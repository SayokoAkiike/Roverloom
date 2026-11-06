#pragma once

#include "CoreMinimal.h"

// The C++ side of python/src/roverloom/frames.py: the only place that knows both the contract frame and Unreal's.
// Contract: site frame, right-handed, +X east, +Y north, +Z up, SI units; body FLU. Unreal: left-handed, X forward,
// Y right, Z up, centimeters. Quaternions rotate a body vector into the world frame.
// Each function matches the Python function of the same name and schemas/conformance/frame_vectors.json.
// The ENU-to-NED helpers of frames.py are not ported; nothing in Unreal uses them yet.
namespace RoverloomFrames
{
	inline constexpr double UnrealCmPerM = 100.0;

	// Also for velocities: m/s become cm/s. Unreal's +Y is the site's -Y.
	inline FVector SiteToUnrealPosition(const FVector& PositionM)
	{
		return FVector(PositionM.X * UnrealCmPerM, -PositionM.Y * UnrealCmPerM, PositionM.Z * UnrealCmPerM);
	}

	inline FVector UnrealToSitePosition(const FVector& PositionCm)
	{
		return FVector(PositionCm.X / UnrealCmPerM, -PositionCm.Y / UnrealCmPerM, PositionCm.Z / UnrealCmPerM);
	}

	// A mirror across the XZ plane negates the X and Z parts. The conversion is its own inverse.
	inline FQuat SiteToUnrealQuat(const FQuat& Q)
	{
		return FQuat(-Q.X, Q.Y, -Q.Z, Q.W);
	}

	inline FQuat UnrealToSiteQuat(const FQuat& Q)
	{
		return SiteToUnrealQuat(Q);
	}

	// Angular velocity is an axial vector: under a mirror it picks up an extra sign change. Its own inverse.
	inline FVector SiteToUnrealAngularVelocity(const FVector& OmegaRadps)
	{
		return FVector(-OmegaRadps.X, OmegaRadps.Y, -OmegaRadps.Z);
	}

	inline FVector UnrealToSiteAngularVelocity(const FVector& OmegaRadps)
	{
		return SiteToUnrealAngularVelocity(OmegaRadps);
	}

	// Contract: positive turns left. Unreal: positive yaw turns right, seen from above.
	inline double SiteYawRateToUnreal(double YawRateRadps)
	{
		return -YawRateRadps;
	}

	// FRotator yaw in degrees. FRotator uses degrees and the contract uses radians.
	inline double SiteYawToUnrealDegrees(double YawRad)
	{
		return -FMath::RadiansToDegrees(YawRad);
	}

	inline double UnrealYawDegreesToSite(double YawDeg)
	{
		return -FMath::DegreesToRadians(YawDeg);
	}
}
