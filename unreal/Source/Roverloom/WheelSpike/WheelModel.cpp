#include "WheelModel.h"

namespace RoverloomWheel
{
	double SpringRateFor(double LoadForce, double StaticCompressionCm)
	{
		return LoadForce / StaticCompressionCm;
	}

	double DamperRateFor(double SpringRate, double SprungMassKg, double DampingRatio)
	{
		return 2.0 * DampingRatio * FMath::Sqrt(SpringRate * SprungMassKg);
	}

	FWheelResult StepWheel(const FWheelParams& Params, const FWheelContact& Contact, EWheelMode Mode, double TargetSpinRadps,
		double Dt, double& InOutSpinRadps)
	{
		const double R = Params.RadiusCm;
		const double I = Params.InertiaKgCm2;
		const double Omega = InOutSpinRadps;
		const double Target = Mode == EWheelMode::Brake ? 0.0 : TargetSpinRadps;
		const double Limit = Mode == EWheelMode::Brake ? Params.BrakeMaxTorque : Params.MotorMaxTorque;

		FWheelResult Out;
		Out.LongVelocity = FVector::DotProduct(Contact.ContactVelocity, Contact.Forward);
		Out.LatVelocity = FVector::DotProduct(Contact.ContactVelocity, Contact.Lateral);
		Out.SlipCmps = Omega * R - Out.LongVelocity;

		// Torque that brings the spin to the target this step against a ground force, within the limit.
		auto Servo = [&](double GroundForce)
		{
			return Mode == EWheelMode::Coast ? 0.0 : FMath::Clamp(I * (Target - Omega) / Dt + GroundForce * R, -Limit, Limit);
		};
		// Ground force that leaves no slip at the end of the step for a given torque.
		auto StickingForce = [&](double Torque)
		{
			return (Out.SlipCmps / Dt + Torque * R / I) / (R * R / I + 1.0 / Contact.MassLongKg);
		};

		double Torque = 0.0;
		double Long = 0.0;
		double Lat = 0.0;
		if (Contact.bHit)
		{
			Out.NormalForce = FMath::Max(0.0, Params.SpringRate * Contact.CompressionCm + Params.DamperRate * Contact.CompressionRateCmps);
			Out.FrictionLimit = Params.Friction * Out.NormalForce;

			if (Mode == EWheelMode::Coast)
			{
				Long = StickingForce(0.0);
			}
			else
			{
				Long = Contact.MassLongKg * (Target * R - Out.LongVelocity) / Dt;
				Torque = I * (Target - Omega) / Dt + Long * R;
				if (FMath::Abs(Torque) > Limit)
				{
					Torque = FMath::Clamp(Torque, -Limit, Limit);
					Long = StickingForce(Torque);
				}
			}
			Lat = -Contact.MassLatKg * Out.LatVelocity / Dt;

			const double Magnitude = FMath::Sqrt(Long * Long + Lat * Lat);
			if (Magnitude > Out.FrictionLimit)
			{
				const double Scale = Magnitude > 0.0 ? Out.FrictionLimit / Magnitude : 0.0;
				Long *= Scale;
				Lat *= Scale;
				Out.bSaturated = true;
				Torque = Servo(Long);
			}
		}
		else
		{
			Torque = Servo(0.0);
		}

		InOutSpinRadps = Omega + Dt * (Torque - Long * R) / I;
		Out.LongForce = Long;
		Out.LatForce = Lat;
		(Mode == EWheelMode::Brake ? Out.BrakeTorque : Out.MotorTorque) = Torque;
		return Out;
	}
}
