#include "Misc/AutomationTest.h"

#include "WheelModel.h"

#if WITH_DEV_AUTOMATION_TESTS

using namespace RoverloomWheel;

namespace
{
	const double Gravity = 371.0;
	const double Mass = 142.25;

	// A body on flat ground with contacts below it. A slope is modeled by tilting gravity about Y, so downhill is -X.
	// Steps integrate in Chaos's order: v += dt (g + F / M), w += dt I^-1 T, from the velocity at the start of the step.
	struct FTestRig
	{
		FWheelParams Params;
		FBodyState Body;
		TArray<FWheelContact> Contacts;
		TArray<double> Spins;
		double YawInertia = 0.0; // 0 locks all rotation.

		FTestRig(double InMass, double Friction, double SlopeDeg, const TArray<FVector>& Points, double InYawInertia = 0.0)
		{
			const double Slope = FMath::DegreesToRadians(SlopeDeg);
			const double Load = InMass * Gravity * FMath::Cos(Slope) / Points.Num();
			Params.Friction = Friction;
			Params.SpringRate = SpringRateFor(Load, 5.0);
			Body.InvMass = 1.0 / InMass;
			Body.Acceleration = FVector(-Gravity * FMath::Sin(Slope), 0.0, -Gravity * FMath::Cos(Slope));
			YawInertia = InYawInertia;
			if (YawInertia > 0.0)
			{
				Body.InvInertia[2] = FVector(0.0, 0.0, 1.0 / YawInertia);
			}
			for (const FVector& Point : Points)
			{
				FWheelContact Contact;
				Contact.bHit = true;
				Contact.CompressionCm = 5.0;
				Contact.Point = Point;
				Contacts.Add(Contact);
			}
			Spins.Init(0.0, Points.Num());
		}

		TArray<FWheelResult> Step(const TArray<FWheelCommand>& Commands, double Dt, FSolveStats* OutStats = nullptr)
		{
			TArray<FWheelResult> Results;
			FSolveStats Stats;
			SolveWheels(Params, Body, Contacts, Commands, Dt, Spins, Results, Stats);
			FVector Force = FVector::ZeroVector;
			FVector Torque = FVector::ZeroVector;
			for (int32 Index = 0; Index < Contacts.Num(); ++Index)
			{
				const FWheelContact& Contact = Contacts[Index];
				const FVector F = Results[Index].NormalForce * Contact.Normal + Results[Index].LongForce * Contact.Forward
					+ Results[Index].LatForce * Contact.Lateral;
				Force += F;
				Torque += FVector::CrossProduct(Contact.Point - Body.CenterOfMass, F);
			}
			Body.LinearVelocity += Dt * (Body.Acceleration + Force * Body.InvMass);
			Body.AngularVelocity += Dt * Body.AngularResponse(Torque);
			if (OutStats)
			{
				*OutStats = Stats;
			}
			return Results;
		}

		// Largest contact speed in the ground plane, after the last step.
		double LargestContactSpeed() const
		{
			double Largest = 0.0;
			for (const FWheelContact& Contact : Contacts)
			{
				const FVector V = Body.VelocityAt(Contact.Point);
				Largest = FMath::Max(Largest, FVector(V.X, V.Y, 0.0).Size());
			}
			return Largest;
		}
	};

	TArray<FWheelCommand> All(int32 Count, EWheelMode Mode, double Target = 0.0)
	{
		TArray<FWheelCommand> Commands;
		Commands.Init({Mode, Target}, Count);
		return Commands;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRoverloomWheelModelTest,
	"Roverloom.WheelSpike.Model",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRoverloomWheelModelTest::RunTest(const FString& Parameters)
{
	const double Dt = 1.0 / 60.0;
	const FVector Below(0.0, 0.0, -45.0);

	// Flat: a wheel rolling with the ground at its target needs no traction.
	{
		FTestRig Rig(Mass, 0.5, 0.0, {Below});
		Rig.Body.LinearVelocity = FVector(50.0, 0.0, 0.0);
		Rig.Spins[0] = 2.0;
		const TArray<FWheelResult> Out = Rig.Step(All(1, EWheelMode::Drive, 2.0), Dt);
		TestEqual(TEXT("Flat: normal force is k x"), Out[0].NormalForce, Mass * Gravity, 1e-6);
		TestEqual(TEXT("Flat: no traction"), Out[0].LongForce, 0.0, 1e-6);
		TestEqual(TEXT("Flat: spin kept"), Rig.Spins[0], 2.0, 1e-9);
		TestEqual(TEXT("Flat: speed kept"), Rig.Body.LinearVelocity.X, 50.0, 1e-6);
	}

	// Slope, one contact: braking on 10 degrees holds with gravity in the prediction, at every step size.
	for (const double Step : {1.0 / 60.0, 1.0 / 120.0, 1.0 / 240.0})
	{
		FTestRig Rig(Mass, 0.6, 10.0, {Below});
		TArray<FWheelResult> Out;
		for (int32 Index = 0; Index < FMath::RoundToInt(2.0 / Step); ++Index)
		{
			Out = Rig.Step(All(1, EWheelMode::Brake), Step);
		}
		TestTrue(*FString::Printf(TEXT("Slope hold at %.0f Hz: no creep"), 1.0 / Step), Rig.LargestContactSpeed() < 1e-6);
		TestEqual(*FString::Printf(TEXT("Slope hold at %.0f Hz: traction is M g sin"), 1.0 / Step), Out[0].LongForce,
			Mass * Gravity * FMath::Sin(FMath::DegreesToRadians(10.0)), 1e-3);
		TestEqual(TEXT("Slope hold: gravity's step change is recorded"), Out[0].GravityDvLong,
			-Step * Gravity * FMath::Sin(FMath::DegreesToRadians(10.0)), 1e-9);
		TestFalse(TEXT("Slope hold: not saturated"), Out[0].bSaturated);
	}

	// Several contacts: two wheels across a yawing body push together on the slope under a zero command.
	{
		const double PairMass = 2.0 * Mass;
		FTestRig Rig(PairMass, 0.6, 10.0, {FVector(0.0, -103.7, -45.0), FVector(0.0, 103.7, -45.0)}, 2.0e6);
		TArray<FWheelResult> Out;
		FSolveStats Stats;
		for (int32 Index = 0; Index < 120; ++Index)
		{
			Out = Rig.Step(All(2, EWheelMode::Drive), Dt, &Stats);
		}
		TestTrue(TEXT("Pair: no creep"), Rig.LargestContactSpeed() < 1e-6);
		TestTrue(TEXT("Pair: solve converged"), Stats.bConverged);
		TestEqual(TEXT("Pair: total traction is M g sin"), Out[0].LongForce + Out[1].LongForce,
			PairMass * Gravity * FMath::Sin(FMath::DegreesToRadians(10.0)), 1e-3);
		TestTrue(TEXT("Pair: no yaw"), FMath::Abs(Rig.Body.AngularVelocity.Z) < 1e-9);
	}

	// Several contacts, uneven: three wheels at different places, yaw free, braking on the slope.
	{
		FTestRig Rig(3.0 * Mass, 0.6, 10.0, {FVector(97.6, -103.7, -45.0), FVector(-97.6, -103.7, -45.0), FVector(0.0, 103.7, -45.0)},
			3.0e6);
		FSolveStats Stats;
		for (int32 Index = 0; Index < 120; ++Index)
		{
			Rig.Step(All(3, EWheelMode::Brake), Dt, &Stats);
		}
		TestTrue(TEXT("Three contacts: no creep at any contact"), Rig.LargestContactSpeed() < 1e-6);
		TestTrue(TEXT("Three contacts: solve converged"), Stats.bConverged);
	}

	// Spin in place: opposite targets on the pair turn the body with no sideways slip.
	{
		FTestRig Rig(2.0 * Mass, 0.6, 0.0, {FVector(0.0, -103.7, -45.0), FVector(0.0, 103.7, -45.0)}, 2.0e6);
		TArray<FWheelCommand> Commands = {{EWheelMode::Drive, 1.0}, {EWheelMode::Drive, -1.0}};
		TArray<FWheelResult> Out;
		for (int32 Index = 0; Index < 120; ++Index)
		{
			Out = Rig.Step(Commands, Dt);
		}
		TestEqual(TEXT("Spin in place: yaw rate is rim speed over half track"), Rig.Body.AngularVelocity.Z, 25.0 / 103.7, 1e-6);
		TestEqual(TEXT("Spin in place: no body speed"), Rig.Body.LinearVelocity.Size(), 0.0, 1e-6);
		TestEqual(TEXT("Spin in place: no end slip"), Out[0].EndSlipCmps, 0.0, 1e-6);
	}

	// Torque limit first: at mu 0.5 the motor's limit binds before friction does, so nothing slips.
	{
		FTestRig Rig(Mass, 0.5, 0.0, {Below});
		const TArray<FWheelResult> Out = Rig.Step(All(1, EWheelMode::Drive, 20.0), Dt);
		TestFalse(TEXT("Torque-limited: not saturated"), Out[0].bSaturated);
		TestEqual(TEXT("Torque-limited: motor at its limit"), Out[0].MotorTorque, Rig.Params.MotorMaxTorque, 1e-6);
		TestEqual(TEXT("Torque-limited: no end slip"), Out[0].EndSlipCmps, 0.0, 1e-6);
	}

	// Friction saturation, driving: at mu 0.3 the demand is limited to mu Fz, and the wheel spins up.
	{
		FTestRig Rig(Mass, 0.3, 0.0, {Below});
		const TArray<FWheelResult> Out = Rig.Step(All(1, EWheelMode::Drive, 20.0), Dt);
		TestTrue(TEXT("Spin-up: saturated"), Out[0].bSaturated);
		TestEqual(TEXT("Spin-up: traction at the friction limit"), FMath::Abs(Out[0].LongForce), Out[0].FrictionLimit, 1e-6);
		TestTrue(TEXT("Spin-up: motor within its limit"), FMath::Abs(Out[0].MotorTorque) <= Rig.Params.MotorMaxTorque + 1e-6);
	}

	// Friction saturation, on a slope: at mu 0.1 a braked wheel slides at g (sin - mu cos).
	{
		FTestRig Rig(Mass, 0.1, 10.0, {Below});
		TArray<FWheelResult> Out;
		for (int32 Index = 0; Index < 60; ++Index)
		{
			Out = Rig.Step(All(1, EWheelMode::Brake), Dt);
		}
		const double Slope = FMath::DegreesToRadians(10.0);
		TestTrue(TEXT("Slope slide: saturated"), Out[0].bSaturated);
		TestEqual(TEXT("Slope slide: wheel locked"), Rig.Spins[0], 0.0, 1e-9);
		TestEqual(TEXT("Slope slide: speed after 1 s"), Rig.Body.LinearVelocity.X,
			-Gravity * (FMath::Sin(Slope) - 0.1 * FMath::Cos(Slope)), 1e-6);
	}

	// Friction circle: a combined demand stays on the circle and opposes sliding.
	{
		FTestRig Rig(Mass, 0.5, 0.0, {Below});
		Rig.Body.LinearVelocity = FVector(300.0, 400.0, 0.0);
		const TArray<FWheelResult> Out = Rig.Step(All(1, EWheelMode::Brake), Dt);
		TestEqual(TEXT("Circle: |F| equals mu Fz"), FMath::Sqrt(FMath::Square(Out[0].LongForce) + FMath::Square(Out[0].LatForce)),
			Out[0].FrictionLimit, 1e-6);
		TestTrue(TEXT("Circle: forces oppose sliding"), Out[0].LongForce < 0.0 && Out[0].LatForce < 0.0);
		TestEqual(TEXT("Circle: locked wheel stays locked"), Rig.Spins[0], 0.0, 1e-9);
	}

	// Time step: a torque-limited start reaches the same speed after 0.5 s at 60 and 120 Hz, before the target.
	{
		double Speeds[2] = {};
		const double Steps[2] = {1.0 / 60.0, 1.0 / 120.0};
		for (int32 Case = 0; Case < 2; ++Case)
		{
			FTestRig Rig(Mass, 0.6, 0.0, {Below});
			for (int32 Index = 0; Index < FMath::RoundToInt(0.5 / Steps[Case]); ++Index)
			{
				Rig.Step(All(1, EWheelMode::Drive, 4.0), Steps[Case]);
			}
			Speeds[Case] = Rig.Body.LinearVelocity.X;
		}
		TestTrue(TEXT("Time step: speeds within 1%"), FMath::Abs(Speeds[1] / Speeds[0] - 1.0) < 0.01);
	}

	// No contact: no ground force, and the motor still turns the wheel within its limit.
	{
		FTestRig Rig(Mass, 0.5, 0.0, {Below});
		Rig.Contacts[0].bHit = false;
		const TArray<FWheelResult> Out = Rig.Step(All(1, EWheelMode::Drive, 2.0), Dt);
		TestEqual(TEXT("Airborne: no normal force"), Out[0].NormalForce, 0.0);
		TestTrue(TEXT("Airborne: spin moves toward target"), Rig.Spins[0] > 0.0 && Rig.Spins[0] <= 2.0 + 1e-9);
	}

	// Coasting: no torque.
	{
		FTestRig Rig(Mass, 0.5, 0.0, {Below});
		Rig.Body.LinearVelocity = FVector(25.0, 0.0, 0.0);
		Rig.Spins[0] = 1.0;
		const TArray<FWheelResult> Out = Rig.Step(All(1, EWheelMode::Coast), Dt);
		TestEqual(TEXT("Coast: no motor torque"), Out[0].MotorTorque, 0.0);
	}
	return true;
}

#endif
