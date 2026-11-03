#pragma once

#include "CoreMinimal.h"

// Wheel model experiment (Step 5a, phases A and B). See docs/results/unreal-wheel-model/README.md.
// Unreal units: cm, kg, s. Forces in kg cm/s^2, torques in kg cm^2/s^2. No engine world access here.
namespace RoverloomWheel
{
	struct FWheelParams
	{
		double RadiusCm = 25.0;
		double InertiaKgCm2 = 0.4 * 15.0 * 25.0 * 25.0;
		double RestLengthCm = 30.0;
		double SpringRate = 0.0;  // kg/s^2
		double DamperRate = 0.0;  // kg/s
		double Friction = 0.6;
		double MotorMaxTorque = 6.0e5;
		double BrakeMaxTorque = 2.0e6;
	};

	enum class EWheelMode : uint8
	{
		Drive,
		Brake,
		Coast,
	};

	struct FWheelContact
	{
		bool bHit = false;
		double CompressionCm = 0.0;
		double CompressionRateCmps = 0.0; // Positive while compressing.
		FVector Forward = FVector::ForwardVector; // Unit, in the contact plane.
		FVector Lateral = FVector::RightVector;   // Unit, in the contact plane.
		FVector ContactVelocity = FVector::ZeroVector;
		double MassLongKg = 1.0; // This wheel's share of the body's effective mass at the contact.
		double MassLatKg = 1.0;
	};

	struct FWheelResult
	{
		double NormalForce = 0.0;
		double LongForce = 0.0;
		double LatForce = 0.0;
		double FrictionLimit = 0.0;
		double MotorTorque = 0.0;
		double BrakeTorque = 0.0;
		double LongVelocity = 0.0;
		double LatVelocity = 0.0;
		double SlipCmps = 0.0; // Rim speed minus ground speed, before the step.
		bool bSaturated = false;
	};

	// Spring rate for a static compression under a load, and damper rate for a damping ratio.
	double SpringRateFor(double LoadForce, double StaticCompressionCm);
	double DamperRateFor(double SpringRate, double SprungMassKg, double DampingRatio);

	// Advances the wheel's spin by Dt and returns the forces on the body at the contact point.
	FWheelResult StepWheel(const FWheelParams& Params, const FWheelContact& Contact, EWheelMode Mode, double TargetSpinRadps,
		double Dt, double& InOutSpinRadps);
}
