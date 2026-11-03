#include "WheelModel.h"

namespace RoverloomWheel
{
	namespace
	{
		const int32 MaxPasses = 200;
		const double ToleranceCmps = 1e-7;

		// One tangent direction at one contact. Each wheel has a longitudinal row and a lateral row.
		struct FRow
		{
			FVector Direction;
			FVector Arm;     // r x d
			FVector Angular; // I^-1 (r x d)
		};
	}

	FVector FBodyState::AngularResponse(const FVector& Torque) const
	{
		return FVector(FVector::DotProduct(InvInertia[0], Torque), FVector::DotProduct(InvInertia[1], Torque),
			FVector::DotProduct(InvInertia[2], Torque));
	}

	FVector FBodyState::VelocityAt(const FVector& Point) const
	{
		return LinearVelocity + FVector::CrossProduct(AngularVelocity, Point - CenterOfMass);
	}

	double SpringRateFor(double LoadForce, double StaticCompressionCm)
	{
		return LoadForce / StaticCompressionCm;
	}

	double DamperRateFor(double SpringRate, double SprungMassKg, double DampingRatio)
	{
		return 2.0 * DampingRatio * FMath::Sqrt(SpringRate * SprungMassKg);
	}

	void SolveWheels(const FWheelParams& Params, const FBodyState& Body, TConstArrayView<FWheelContact> Contacts,
		TConstArrayView<FWheelCommand> Commands, double Dt, TArrayView<double> InOutSpinRadps, TArray<FWheelResult>& OutResults,
		FSolveStats& OutStats)
	{
		const int32 Count = Contacts.Num();
		const double R = Params.RadiusCm;
		const double I = Params.InertiaKgCm2;
		OutResults.SetNum(Count);
		OutStats = FSolveStats();

		// Normal loads, and the body's motion over the step from them and the known forces alone.
		FVector Force = Body.ExternalForce;
		FVector Torque = FVector::ZeroVector;
		for (int32 Index = 0; Index < Count; ++Index)
		{
			const FWheelContact& Contact = Contacts[Index];
			FWheelResult& Out = OutResults[Index];
			Out = FWheelResult();
			if (Contact.bHit)
			{
				Out.NormalForce = FMath::Max(0.0, Params.SpringRate * Contact.CompressionCm + Params.DamperRate * Contact.CompressionRateCmps);
				Out.FrictionLimit = Params.Friction * Out.NormalForce;
				Force += Out.NormalForce * Contact.Normal;
				Torque += FVector::CrossProduct(Contact.Point - Body.CenterOfMass, Out.NormalForce * Contact.Normal);
			}
		}
		FBodyState Known = Body;
		Known.LinearVelocity += Dt * (Body.Acceleration + Force * Body.InvMass);
		Known.AngularVelocity += Dt * Body.AngularResponse(Torque);

		// Rows, their coupling K (velocity change at row a per unit force at row b, per unit time), and velocities.
		TArray<FRow> Rows;
		TArray<int32> FirstRow;
		FirstRow.Init(INDEX_NONE, Count);
		TArray<double> Velocity;
		for (int32 Index = 0; Index < Count; ++Index)
		{
			const FWheelContact& Contact = Contacts[Index];
			FWheelResult& Out = OutResults[Index];
			const FVector Start = Body.VelocityAt(Contact.Point);
			Out.LongVelocity = FVector::DotProduct(Start, Contact.Forward);
			Out.LatVelocity = FVector::DotProduct(Start, Contact.Lateral);
			Out.SlipCmps = InOutSpinRadps[Index] * R - Out.LongVelocity;
			if (!Contact.bHit)
			{
				continue;
			}
			FirstRow[Index] = Rows.Num();
			for (const FVector& Direction : {Contact.Forward, Contact.Lateral})
			{
				const FVector Arm = FVector::CrossProduct(Contact.Point - Body.CenterOfMass, Direction);
				Rows.Add({Direction, Arm, Body.AngularResponse(Arm)});
				Velocity.Add(FVector::DotProduct(Known.VelocityAt(Contact.Point), Direction));
			}
			Out.KnownDvLong = Velocity[FirstRow[Index]] - Out.LongVelocity;
			Out.KnownDvLat = Velocity[FirstRow[Index] + 1] - Out.LatVelocity;
			Out.GravityDvLong = Dt * FVector::DotProduct(Body.Acceleration, Contact.Forward);
		}
		const int32 RowCount = Rows.Num();
		TArray<double> K;
		K.SetNumZeroed(RowCount * RowCount);
		for (int32 A = 0; A < RowCount; ++A)
		{
			for (int32 B = 0; B < RowCount; ++B)
			{
				K[A * RowCount + B] = FVector::DotProduct(Rows[A].Direction, Rows[B].Direction) * Body.InvMass
					+ FVector::DotProduct(Rows[A].Arm, Rows[B].Angular);
			}
		}
		TArray<double> Solved;
		Solved.SetNumZeroed(RowCount);
		TArray<double> Torques;
		Torques.SetNumZeroed(Count);

		auto Apply = [&](int32 Row, double Change)
		{
			for (int32 A = 0; A < RowCount; ++A)
			{
				Velocity[A] += K[A * RowCount + Row] * Change * Dt;
			}
			Solved[Row] += Change;
		};

		// Projected Gauss-Seidel over the wheels: each pass re-solves one wheel against all the others' current forces.
		for (int32 Pass = 0; Pass < MaxPasses && RowCount > 0; ++Pass)
		{
			double LargestChange = 0.0;
			for (int32 Index = 0; Index < Count; ++Index)
			{
				const int32 Long = FirstRow[Index];
				if (Long == INDEX_NONE)
				{
					continue;
				}
				const int32 Lat = Long + 1;
				const FWheelCommand& Command = Commands[Index];
				FWheelResult& Out = OutResults[Index];
				const double Omega = InOutSpinRadps[Index];
				const double Target = Command.Mode == EWheelMode::Brake ? 0.0 : Command.TargetSpinRadps;
				const double Limit = Command.Mode == EWheelMode::Brake ? Params.BrakeMaxTorque : Params.MotorMaxTorque;
				const double KLong = K[Long * RowCount + Long];
				const double OldLong = Solved[Long];
				const double OldLat = Solved[Lat];

				// Ground force that leaves no slip at the end of the step for a given torque.
				auto Sticking = [&](double WheelTorque)
				{
					return (Omega * R - Velocity[Long] + KLong * OldLong * Dt + Dt * WheelTorque * R / I) / (Dt * (R * R / I + KLong));
				};
				auto Servo = [&](double GroundForce)
				{
					return Command.Mode == EWheelMode::Coast ? 0.0
						: FMath::Clamp(I * (Target - Omega) / Dt + GroundForce * R, -Limit, Limit);
				};

				double NewLong = 0.0;
				double WheelTorque = 0.0;
				if (Command.Mode == EWheelMode::Coast)
				{
					NewLong = Sticking(0.0);
				}
				else
				{
					NewLong = OldLong + (Target * R - Velocity[Long]) / (KLong * Dt);
					WheelTorque = I * (Target - Omega) / Dt + NewLong * R;
					if (FMath::Abs(WheelTorque) > Limit)
					{
						WheelTorque = FMath::Clamp(WheelTorque, -Limit, Limit);
						NewLong = Sticking(WheelTorque);
					}
				}
				Apply(Long, NewLong - OldLong);
				double NewLat = OldLat - Velocity[Lat] / (K[Lat * RowCount + Lat] * Dt);

				Out.bSaturated = false;
				const double Magnitude = FMath::Sqrt(NewLong * NewLong + NewLat * NewLat);
				if (Magnitude > Out.FrictionLimit)
				{
					const double Scale = Magnitude > 0.0 ? Out.FrictionLimit / Magnitude : 0.0;
					Apply(Long, NewLong * Scale - NewLong);
					NewLong *= Scale;
					NewLat *= Scale;
					Out.bSaturated = true;
					WheelTorque = Servo(NewLong);
				}
				Apply(Lat, NewLat - OldLat);
				Torques[Index] = WheelTorque;
				LargestChange = FMath::Max(LargestChange, FMath::Abs(NewLong - OldLong) * KLong * Dt);
				LargestChange = FMath::Max(LargestChange, FMath::Abs(NewLat - OldLat) * K[Lat * RowCount + Lat] * Dt);
			}
			OutStats.Iterations = Pass + 1;
			OutStats.LastChangeCmps = LargestChange;
			if (LargestChange < ToleranceCmps)
			{
				OutStats.bConverged = true;
				break;
			}
		}

		for (int32 Index = 0; Index < Count; ++Index)
		{
			FWheelResult& Out = OutResults[Index];
			const FWheelCommand& Command = Commands[Index];
			const int32 Long = FirstRow[Index];
			if (Long == INDEX_NONE)
			{
				const double Target = Command.Mode == EWheelMode::Brake ? 0.0 : Command.TargetSpinRadps;
				const double Limit = Command.Mode == EWheelMode::Brake ? Params.BrakeMaxTorque : Params.MotorMaxTorque;
				Torques[Index] = Command.Mode == EWheelMode::Coast ? 0.0
					: FMath::Clamp(I * (Target - InOutSpinRadps[Index]) / Dt, -Limit, Limit);
			}
			else
			{
				Out.LongForce = Solved[Long];
				Out.LatForce = Solved[Long + 1];
			}
			InOutSpinRadps[Index] += Dt * (Torques[Index] - Out.LongForce * R) / I;
			if (Long != INDEX_NONE)
			{
				Out.EndSlipCmps = InOutSpinRadps[Index] * R - Velocity[Long];
				Out.EndLatVelocity = Velocity[Long + 1];
			}
			(Command.Mode == EWheelMode::Brake ? Out.BrakeTorque : Out.MotorTorque) = Torques[Index];
		}
	}
}
