#include "Misc/AutomationTest.h"

#include "WheelModel.h"

#if WITH_DEV_AUTOMATION_TESTS

using namespace RoverloomWheel;

namespace
{
	FWheelParams TestParams()
	{
		FWheelParams Params;
		Params.SpringRate = 10000.0;
		Params.Friction = 0.5;
		return Params;
	}

	FWheelContact TestContact(double CompressionCm, const FVector& Velocity)
	{
		FWheelContact Contact;
		Contact.bHit = true;
		Contact.CompressionCm = CompressionCm;
		Contact.ContactVelocity = Velocity;
		Contact.MassLongKg = 100.0;
		Contact.MassLatKg = 100.0;
		return Contact;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRoverloomWheelModelTest,
	"Roverloom.WheelSpike.Model",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRoverloomWheelModelTest::RunTest(const FString& Parameters)
{
	const FWheelParams Params = TestParams();
	const double Dt = 1.0 / 60.0;

	// Sticking: a wheel rolling with the ground and a matching target needs no force.
	double Spin = 2.0;
	FWheelResult Out = StepWheel(Params, TestContact(5.0, FVector(50.0, 0.0, 0.0)), EWheelMode::Drive, 2.0, Dt, Spin);
	TestEqual(TEXT("Rolling: normal force is k x"), Out.NormalForce, 50000.0, 1e-6);
	TestEqual(TEXT("Rolling: no slip"), Out.SlipCmps, 0.0, 1e-9);
	TestEqual(TEXT("Rolling: no traction"), Out.LongForce, 0.0, 1e-6);
	TestEqual(TEXT("Rolling: spin kept"), Spin, 2.0, 1e-9);

	// Torque limit first: at mu 0.5 the motor's limit binds before friction does, so nothing slips.
	Spin = 0.0;
	Out = StepWheel(Params, TestContact(5.0, FVector::ZeroVector), EWheelMode::Drive, 20.0, Dt, Spin);
	TestFalse(TEXT("Torque-limited: not saturated"), Out.bSaturated);
	TestEqual(TEXT("Torque-limited: motor at its limit"), Out.MotorTorque, Params.MotorMaxTorque, 1e-6);

	// Saturation: at mu 0.3 the demand is limited to mu Fz, and the wheel spins up.
	FWheelParams Slippery = Params;
	Slippery.Friction = 0.3;
	Spin = 0.0;
	Out = StepWheel(Slippery, TestContact(5.0, FVector::ZeroVector), EWheelMode::Drive, 20.0, Dt, Spin);
	TestTrue(TEXT("Spin-up: saturated"), Out.bSaturated);
	TestEqual(TEXT("Spin-up: traction at the friction limit"), FMath::Abs(Out.LongForce), Out.FrictionLimit, 1e-6);
	TestTrue(TEXT("Spin-up: motor within its limit"), FMath::Abs(Out.MotorTorque) <= Params.MotorMaxTorque + 1e-6);

	// Friction circle: combined demand stays on the circle.
	Spin = 0.0;
	Out = StepWheel(Params, TestContact(5.0, FVector(30.0, 40.0, 0.0)), EWheelMode::Brake, 0.0, Dt, Spin);
	TestEqual(TEXT("Circle: |F| equals mu Fz"), FMath::Sqrt(Out.LongForce * Out.LongForce + Out.LatForce * Out.LatForce),
		Out.FrictionLimit, 1e-6);
	TestTrue(TEXT("Circle: forces oppose sliding"), Out.LongForce < 0.0 && Out.LatForce < 0.0);
	TestEqual(TEXT("Brake: locked wheel stays locked"), Spin, 0.0, 1e-9);

	// No contact: no ground force, and the motor still turns the wheel within its limit.
	Spin = 0.0;
	FWheelContact Air;
	Out = StepWheel(Params, Air, EWheelMode::Drive, 2.0, Dt, Spin);
	TestEqual(TEXT("Airborne: no normal force"), Out.NormalForce, 0.0);
	TestTrue(TEXT("Airborne: spin moves toward target"), Spin > 0.0 && Spin <= 2.0 + 1e-9);

	// Coasting: no torque.
	Spin = 1.0;
	Out = StepWheel(Params, TestContact(5.0, FVector(25.0, 0.0, 0.0)), EWheelMode::Coast, 0.0, Dt, Spin);
	TestEqual(TEXT("Coast: no motor torque"), Out.MotorTorque, 0.0);
	return true;
}

#endif
