#pragma once

#include "CoreMinimal.h"

// Physics spike only (Step 5a). Unreal units throughout: cm, kg, s, degrees.
// X forward, Y right, Z up. Nothing here uses contract units or frames.
namespace RoverloomSpike
{
	// From rovers/designs/pathfinder_6w.json, compiled by roverloom.rover_builder at e5a48f1.
	constexpr double TotalMassKg = 853.5;
	constexpr double WheelRadiusCm = 25.0;
	constexpr double WheelWidthCm = 20.0; // Not represented: wheels are spheres.
	constexpr double WheelBaseHalfCm = 97.6;
	constexpr double HalfTrackCm = 103.7;
	constexpr double MaxSpeedCmps = 50.0;
	constexpr double MaxYawRateDegps = 28.178; // 0.4918 rad/s

	// Spike assumptions, not part of the design.
	constexpr double WheelMassKg = 15.0;
	constexpr double ChassisMassKg = TotalMassKg - 6.0 * WheelMassKg;
	constexpr double ChassisLengthCm = 200.0;
	constexpr double ChassisWidthCm = 150.0;
	constexpr double ChassisHeightCm = 40.0;
	constexpr double ChassisBottomCm = 55.0;
	constexpr double Friction = 0.6;
	constexpr double MarsGravityZ = -371.0; // cm/s^2
	constexpr double DriveDamping = 1.0e7;  // Force mode, before Chaos's 1.5 scale
	constexpr double DriveMaxTorque = 1.0e6; // kg cm^2 / s^2, which is 100 N m

	// The twist drive target is in revolutions per second about the joint's X axis, which points along the
	// chassis's right axis. Its sign relative to rolling forward is measured by the "probe" scenario:
	// with +1, a target for rolling forward turned the wheels backward at the same speed.
	constexpr double DriveTwistSign = -1.0;

	constexpr int32 NumWheels = 6;

	// Order: front, middle, rear; left before right.
	inline FVector WheelCenter(int32 Index)
	{
		static const double Xs[3] = {WheelBaseHalfCm, 0.0, -WheelBaseHalfCm};
		const double Y = (Index % 2 == 0) ? -HalfTrackCm : HalfTrackCm;
		return FVector(Xs[Index / 2], Y, WheelRadiusCm);
	}

	inline bool IsLeftWheel(int32 Index) { return Index % 2 == 0; }

	// Skid steering. YawRateDegps is Unreal yaw rate: positive turns right, seen from above.
	// Returns wheel rim speeds in cm/s after clamping the command to the design limits.
	inline void SkidRimSpeeds(double ForwardCmps, double YawRateDegps, double& OutLeftCmps, double& OutRightCmps)
	{
		const double V = FMath::Clamp(ForwardCmps, -MaxSpeedCmps, MaxSpeedCmps);
		const double R = FMath::DegreesToRadians(FMath::Clamp(YawRateDegps, -MaxYawRateDegps, MaxYawRateDegps));
		OutLeftCmps = V + R * HalfTrackCm;
		OutRightCmps = V - R * HalfTrackCm;
	}

	inline double RimSpeedToSpinRadps(double RimCmps) { return RimCmps / WheelRadiusCm; }
}
