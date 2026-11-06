#pragma once

#include "CoreMinimal.h"

#include "CommandRouter.h"

// pathfinder_6w on the provisional drive model P: the WheelSpike rig of phase C, unchanged.
// Limits come from rover_builder's compile of rovers/designs/pathfinder_6w.json (0.5 m/s, 0.4918 rad/s, 853.5 kg).
// Geometry and mass are phase C's (WheelSpikeGameMode.cpp). Unreal units: cm, kg, s.
namespace RoverloomRover
{
	inline constexpr double MaxSpeedMps = 0.5;
	inline constexpr double MaxYawRateRadps = 0.4918;
	inline constexpr double MassKg = 853.5;
	inline constexpr double WheelRadiusCm = 25.0;
	inline constexpr double HalfTrackCm = 103.7;
	inline constexpr double MountXCm = 97.6;
	inline constexpr double MountZCm = -20.0;
	inline constexpr double RideHeightCm = 70.0; // Body center above flat ground at 5 cm compression
	inline constexpr double Friction = 0.6;
	inline const FVector BodySizeCm(200.0, 150.0, 40.0);
	inline constexpr int32 NumWheels = 6;

	// Wheels 0-2 are left (-Y in Unreal) and 3-5 right, each front, middle, rear; the order of phase C.
	FVector WheelMountCm(int32 Index);

	// Skid steering as in phase C: rim speed v plus or minus yaw rate times half track. Takes a contract action and
	// fills the six wheels' target spins in rad/s, positive rolling forward.
	void SkidSteerTargets(const RoverloomCommand::FAction& Action, TArray<double>& OutTargetsRadps);
}
