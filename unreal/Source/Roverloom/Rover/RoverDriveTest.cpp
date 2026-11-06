#include "Misc/AutomationTest.h"

#include <limits>

#include "CommandRouter.h"
#include "RoverDrive.h"

#if WITH_DEV_AUTOMATION_TESTS

using namespace RoverloomCommand;

namespace
{
	FCommandRouter MakeRouter()
	{
		return FCommandRouter({TEXT("keyboard"), TEXT("agent")}, TEXT("keyboard"), RoverloomRover::MaxSpeedMps, RoverloomRover::MaxYawRateRadps);
	}
}

// Expected values are python/src/roverloom/command.py's CommandRouter on the same inputs, run on 2026-11-07 with
// limits 0.5 m/s and 0.4918 rad/s.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRoverCommandRouterClampTest, "Roverloom.Rover.CommandRouter.Clamp",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRoverCommandRouterClampTest::RunTest(const FString& Parameters)
{
	struct FCase
	{
		double V, W, AppliedV, AppliedW;
		bool bClamped;
	};
	const FCase Cases[] = {
		{1.0, 1.0, 0.5, 0.4918, true},
		{0.25, -0.3, 0.25, -0.3, false},
		{-0.7, -0.6, -0.5, -0.4918, true},
		{0.5, 0.4918, 0.5, 0.4918, false},
		{0.5000000001, 0.0, 0.5, 0.0, false}, // Within isclose's relative tolerance, so not reported as clamped
	};
	FCommandRouter Router = MakeRouter();
	double TimeS = 0.0;
	for (const FCase& Case : Cases)
	{
		const FCommandRecord Record = Router.Submit(TEXT("keyboard"), {Case.V, Case.W}, TimeS);
		TimeS += 1.0;
		if (!TestTrue(TEXT("accepted"), Record.Applied.IsSet() && Record.RejectedReason.IsEmpty()))
		{
			continue;
		}
		TestEqual(FString::Printf(TEXT("speed for %g"), Case.V), Record.Applied->LinearVelocityMps, Case.AppliedV, 1e-12);
		TestEqual(FString::Printf(TEXT("yaw rate for %g"), Case.W), Record.Applied->YawRateRadps, Case.AppliedW, 1e-12);
		TestTrue(FString::Printf(TEXT("clamped flag for %g, %g"), Case.V, Case.W), Record.bClamped == Case.bClamped);
	}
	TestEqual(TEXT("inactive source"), Router.Submit(TEXT("agent"), {0.1, 0.0}, 5.0).RejectedReason, FString(TEXT("inactive_source")));
	TestEqual(TEXT("unknown source"), Router.Submit(TEXT("rover"), {0.1, 0.0}, 5.0).RejectedReason, FString(TEXT("unknown_source")));
	TestEqual(TEXT("non-finite"), Router.Submit(TEXT("keyboard"), {std::numeric_limits<double>::quiet_NaN(), 0.0}, 5.0).RejectedReason, FString(TEXT("non_finite_action")));
	return true;
}

// The watchdog stops the rover when more than 2 s pass after the last accepted command, as in Python.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRoverCommandRouterWatchdogTest, "Roverloom.Rover.CommandRouter.Watchdog",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRoverCommandRouterWatchdogTest::RunTest(const FString& Parameters)
{
	FCommandRouter Router = MakeRouter();
	TestTrue(TEXT("expired before any command"), Router.WatchdogExpired(0.0));
	TestTrue(TEXT("stop before any command"), Router.Current(0.0).IsStop());
	Router.Submit(TEXT("keyboard"), {0.3, 0.1}, 10.0);
	TestEqual(TEXT("command at once"), Router.Current(10.0).LinearVelocityMps, 0.3);
	TestEqual(TEXT("command at exactly 2 s"), Router.Current(12.0).LinearVelocityMps, 0.3);
	TestFalse(TEXT("not expired at exactly 2 s"), Router.WatchdogExpired(12.0));
	TestTrue(TEXT("stop just after 2 s"), Router.Current(12.000001).IsStop());
	// Handover starts from a stop, so a stale command cannot carry over.
	TestTrue(TEXT("switch to agent"), Router.SetActive(TEXT("agent")));
	TestTrue(TEXT("stopped after handover"), Router.Current(10.5).IsStop());
	TestFalse(TEXT("unknown source refused"), Router.SetActive(TEXT("rover")));
	return true;
}

// Skid steering: the same targets as phase C's CommandSix for the same speed and turn.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRoverSkidSteerTest, "Roverloom.Rover.SkidSteer",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRoverSkidSteerTest::RunTest(const FString& Parameters)
{
	TArray<double> Targets;
	RoverloomRover::SkidSteerTargets({0.5, 0.0}, Targets);
	TestEqual(TEXT("six wheels"), Targets.Num(), 6);
	for (const double Target : Targets)
	{
		TestEqual(TEXT("0.5 m/s is 2 rad/s at 25 cm"), Target, 2.0, 1e-12);
	}
	// A left turn in the contract is a negative Unreal yaw rate: the right side (wheels 3-5) runs faster.
	RoverloomRover::SkidSteerTargets({0.0, 0.4918}, Targets);
	const double Rim = 0.4918 * RoverloomRover::HalfTrackCm / RoverloomRover::WheelRadiusCm;
	for (int32 Index = 0; Index < 6; ++Index)
	{
		TestEqual(FString::Printf(TEXT("wheel %d turning left"), Index), Targets[Index], Index < 3 ? -Rim : Rim, 1e-12);
	}
	TestEqual(TEXT("front left mount"), RoverloomRover::WheelMountCm(0), FVector(97.6, -103.7, -20.0));
	TestEqual(TEXT("rear right mount"), RoverloomRover::WheelMountCm(5), FVector(-97.6, 103.7, -20.0));
	return true;
}

#endif
