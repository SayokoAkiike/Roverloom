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

	// The body at the start of a step, as Chaos will integrate it: v += dt (a + F / M), w += dt I^-1 T.
	struct FBodyState
	{
		double InvMass = 1.0;
		FVector InvInertia[3] = {FVector::ZeroVector, FVector::ZeroVector, FVector::ZeroVector}; // World rows; locked axes removed.
		FVector CenterOfMass = FVector::ZeroVector;
		FVector LinearVelocity = FVector::ZeroVector;
		FVector AngularVelocity = FVector::ZeroVector; // rad/s
		FVector Acceleration = FVector::ZeroVector;    // Known, such as gravity
		FVector ExternalForce = FVector::ZeroVector;   // Known, applied at the center of mass

		FVector AngularResponse(const FVector& Torque) const;
		FVector VelocityAt(const FVector& Point) const;
	};

	struct FWheelContact
	{
		bool bHit = false;
		double CompressionCm = 0.0;
		double CompressionRateCmps = 0.0; // Positive while compressing.
		FVector Point = FVector::ZeroVector;
		FVector Normal = FVector::UpVector;
		FVector Forward = FVector::ForwardVector; // Unit, in the contact plane.
		FVector Lateral = FVector::RightVector;   // Unit, in the contact plane.
	};

	struct FWheelCommand
	{
		EWheelMode Mode = EWheelMode::Drive;
		double TargetSpinRadps = 0.0;
	};

	struct FWheelResult
	{
		double NormalForce = 0.0;
		double LongForce = 0.0;
		double LatForce = 0.0;
		double FrictionLimit = 0.0;
		double MotorTorque = 0.0;
		double BrakeTorque = 0.0;
		double LongVelocity = 0.0;     // Contact velocity at the start of the step
		double LatVelocity = 0.0;
		double SlipCmps = 0.0;         // Rim speed minus ground speed, at the start of the step
		double KnownDvLong = 0.0;      // Change over the step from gravity and other known forces alone
		double KnownDvLat = 0.0;
		double GravityDvLong = 0.0;    // Gravity's part of KnownDvLong
		double EndSlipCmps = 0.0;      // Predicted at the end of the step, with the solved forces
		double EndLatVelocity = 0.0;
		double FrictionPower = 0.0;    // F . u at the end of the step; never positive
		double WheelPower = 0.0;       // Motor or brake torque times end spin
		bool bSaturated = false;       // Sliding: the force is on the friction circle
	};

	struct FSolveStats
	{
		int32 Iterations = 0;
		double LastChangeCmps = 0.0; // Largest velocity change made by the last pass
		bool bConverged = false;
	};

	// Spring rate for a static compression under a load, and damper rate for a damping ratio.
	double SpringRateFor(double LoadForce, double StaticCompressionCm);
	double DamperRateFor(double SpringRate, double SprungMassKg, double DampingRatio);

	// The tangential force on the disk |F| <= Limit that minimizes 0.5 F'WF + A'F, for an end-of-step slip u = A + W F with
	// W symmetric positive definite. Inside the disk u = 0 (stick). On its edge u = -lambda F (slide), opposing the slip.
	FVector2D SolveContactFriction(const FVector2D& A, double W00, double W01, double W11, double Limit, bool& bOutSliding);

	// Solves every wheel's ground force together for one step, and advances each wheel's spin by Dt.
	// Normal loads come from the suspension. Traction is bounded by mu Fz and torques by their limits.
	void SolveWheels(const FWheelParams& Params, const FBodyState& Body, TConstArrayView<FWheelContact> Contacts,
		TConstArrayView<FWheelCommand> Commands, double Dt, TArrayView<double> InOutSpinRadps, TArray<FWheelResult>& OutResults,
		FSolveStats& OutStats);
}
