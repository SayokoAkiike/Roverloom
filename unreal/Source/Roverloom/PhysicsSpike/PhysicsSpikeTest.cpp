#include "Misc/AutomationTest.h"

#include "SpikeParameters.h"

#if WITH_DEV_AUTOMATION_TESTS

using namespace RoverloomSpike;

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRoverloomSpikeSkidTest,
	"Roverloom.PhysicsSpike.SkidSteering",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRoverloomSpikeSkidTest::RunTest(const FString& Parameters)
{
	double Left = 0.0;
	double Right = 0.0;

	SkidRimSpeeds(50.0, 0.0, Left, Right);
	TestEqual(TEXT("Straight: left rim"), Left, 50.0);
	TestEqual(TEXT("Straight: right rim"), Right, 50.0);
	TestEqual(TEXT("50 cm/s on a 25 cm wheel is 2 rad/s"), RimSpeedToSpinRadps(Left), 2.0);

	// Unreal yaw rate is positive to the right, so the left side runs faster.
	SkidRimSpeeds(0.0, 10.0, Left, Right);
	TestTrue(TEXT("Right turn: left faster than right"), Left > 0.0 && Right < 0.0);
	TestEqual(TEXT("Right turn: rim speed is yaw rate times half track"), Left, FMath::DegreesToRadians(10.0) * HalfTrackCm, 1e-9);

	SkidRimSpeeds(500.0, -500.0, Left, Right);
	TestEqual(TEXT("Clamped: mean rim speed"), (Left + Right) / 2.0, MaxSpeedCmps, 1e-9);
	TestEqual(TEXT("Clamped: rim difference"), (Right - Left) / 2.0, FMath::DegreesToRadians(MaxYawRateDegps) * HalfTrackCm, 1e-9);

	TestTrue(TEXT("Wheel 0 is front left"), WheelCenter(0).X > 0.0 && WheelCenter(0).Y < 0.0 && IsLeftWheel(0));
	TestTrue(TEXT("Wheel 5 is rear right"), WheelCenter(5).X < 0.0 && WheelCenter(5).Y > 0.0 && !IsLeftWheel(5));
	TestEqual(TEXT("Masses add up"), ChassisMassKg + NumWheels * WheelMassKg, TotalMassKg, 1e-9);
	return true;
}

#endif
