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

	FVector2D SolveContactFriction(const FVector2D& A, double W00, double W01, double W11, double Limit, bool& bOutSliding)
	{
		// F(lambda) = -(W + lambda I)^-1 A. Its length falls as lambda grows, and |F(lambda)| <= |A| / lambda.
		auto ForceAt = [&](double Lambda)
		{
			const double D00 = W00 + Lambda;
			const double D11 = W11 + Lambda;
			const double Det = D00 * D11 - W01 * W01;
			return FVector2D(-(D11 * A.X - W01 * A.Y) / Det, -(D00 * A.Y - W01 * A.X) / Det);
		};
		const FVector2D Stick = ForceAt(0.0);
		bOutSliding = Stick.Size() > Limit;
		if (!bOutSliding)
		{
			return Stick;
		}
		if (Limit <= 0.0)
		{
			return FVector2D::ZeroVector;
		}
		double Low = 0.0;
		double High = A.Size() / Limit;
		for (int32 Step = 0; Step < 100; ++Step)
		{
			const double Mid = 0.5 * (Low + High);
			(ForceAt(Mid).Size() > Limit ? Low : High) = Mid;
		}
		const FVector2D Edge = ForceAt(High);
		return Edge * (Limit / Edge.Size());
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
				const double KCross = K[Long * RowCount + Lat];
				const double KLat = K[Lat * RowCount + Lat];
				const double OldLong = Solved[Long];
				const double OldLat = Solved[Lat];
				// End-of-step body velocity at the contact with this wheel's own force removed.
				const double FreeLong = Velocity[Long] - Dt * (KLong * OldLong + KCross * OldLat);
				const double FreeLat = Velocity[Lat] - Dt * (KCross * OldLong + KLat * OldLat);

				// First the motor or brake holds the target spin, so the rim moves at Target R.
				FVector2D Traction = FVector2D::ZeroVector;
				double WheelTorque = 0.0;
				bool bSliding = false;
				bool bSpinFree = Command.Mode == EWheelMode::Coast;
				if (!bSpinFree)
				{
					Traction = SolveContactFriction(FVector2D(FreeLong - Target * R, FreeLat), Dt * KLong, Dt * KCross, Dt * KLat,
						Out.FrictionLimit, bSliding);
					WheelTorque = I * (Target - Omega) / Dt + Traction.X * R;
					bSpinFree = FMath::Abs(WheelTorque) > Limit;
				}
				// If that needs more torque than the limit, or the wheel coasts, the torque is fixed and the spin is free.
				if (bSpinFree)
				{
					WheelTorque = Command.Mode == EWheelMode::Coast ? 0.0 : FMath::Clamp(WheelTorque, -Limit, Limit);
					Traction = SolveContactFriction(FVector2D(FreeLong - Omega * R - Dt * WheelTorque * R / I, FreeLat),
						Dt * (KLong + R * R / I), Dt * KCross, Dt * KLat, Out.FrictionLimit, bSliding);
				}
				Apply(Long, Traction.X - OldLong);
				Apply(Lat, Traction.Y - OldLat);
				Out.bSaturated = bSliding;
				const double NewLong = Traction.X;
				const double NewLat = Traction.Y;
				Torques[Index] = WheelTorque;
				LargestChange = FMath::Max(LargestChange, FMath::Abs(NewLong - OldLong) * KLong * Dt);
				LargestChange = FMath::Max(LargestChange, FMath::Abs(NewLat - OldLat) * KLat * Dt);
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
				Out.FrictionPower = Out.LongForce * (Velocity[Long] - InOutSpinRadps[Index] * R) + Out.LatForce * Velocity[Long + 1];
			}
			(Command.Mode == EWheelMode::Brake ? Out.BrakeTorque : Out.MotorTorque) = Torques[Index];
			Out.WheelPower = Torques[Index] * InOutSpinRadps[Index];
		}
	}
}
