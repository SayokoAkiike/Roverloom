#include "RoverDrive.h"

#include "../Bridge/Frames.h"

namespace RoverloomRover
{
	FVector WheelMountCm(int32 Index)
	{
		static const double Xs[3] = {MountXCm, 0.0, -MountXCm};
		const double Y = Index < 3 ? -HalfTrackCm : HalfTrackCm;
		return FVector(Xs[Index % 3], Y, MountZCm);
	}

	void SkidSteerTargets(const RoverloomCommand::FAction& Action, TArray<double>& OutTargetsRadps, double TrackScale)
	{
		// Body-frame forward speed: the site-to-Unreal conversion of (v, 0, 0) is (100 v, 0, 0).
		const double ForwardCmps = RoverloomFrames::SiteToUnrealPosition(FVector(Action.LinearVelocityMps, 0.0, 0.0)).X;
		// Unreal yaw rate is positive to the right, so the left side runs faster for a positive Unreal rate.
		const double Turn = RoverloomFrames::SiteYawRateToUnreal(Action.YawRateRadps) * HalfTrackCm * TrackScale;
		OutTargetsRadps.SetNum(NumWheels);
		for (int32 Index = 0; Index < NumWheels; ++Index)
		{
			OutTargetsRadps[Index] = (Index < 3 ? ForwardCmps + Turn : ForwardCmps - Turn) / WheelRadiusCm;
		}
	}
}
