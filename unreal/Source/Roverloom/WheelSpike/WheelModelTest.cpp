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

	// Angle between a sliding force and the direction opposing the slip it leaves, in degrees.
	double SlideAngleDeg(const FWheelResult& Out)
	{
		const FVector2D Force(Out.LongForce, Out.LatForce);
		const FVector2D Opposing(Out.EndSlipCmps, -Out.EndLatVelocity); // -u, with u = (v_f - w R, v_l)
		if (Force.Size() <= 0.0 || Opposing.Size() <= 1e-9)
		{
			return 0.0;
		}
		// atan2 of cross and dot keeps precision near zero, where acos does not.
		return FMath::RadiansToDegrees(FMath::Atan2(FMath::Abs(FVector2D::CrossProduct(Force, Opposing)), FVector2D::DotProduct(Force, Opposing)));
	}

	// pathfinder_6w on a free body: 853.5 kg box of 200 x 150 x 40 cm, wheels at X +-97.6 and 0, Y +-103.7.
	FTestRig SixWheelRig()
	{
		TArray<FVector> Points;
		for (const double Y : {-103.7, 103.7})
		{
			for (const double X : {97.6, 0.0, -97.6})
			{
				Points.Add(FVector(X, Y, -45.0));
			}
		}
		FTestRig Rig(853.5, 0.6, 0.0, Points);
		const double M = 853.5;
		Rig.Body.InvInertia[0] = FVector(12.0 / (M * (150.0 * 150.0 + 40.0 * 40.0)), 0.0, 0.0);
		Rig.Body.InvInertia[1] = FVector(0.0, 12.0 / (M * (200.0 * 200.0 + 40.0 * 40.0)), 0.0);
		Rig.Body.InvInertia[2] = FVector(0.0, 0.0, 12.0 / (M * (200.0 * 200.0 + 150.0 * 150.0)));
		return Rig;
	}

	TArray<FWheelCommand> TurnInPlace(double YawRateDegps)
	{
		const double Rim = FMath::DegreesToRadians(YawRateDegps) * 103.7;
		TArray<FWheelCommand> Commands;
		for (int32 Index = 0; Index < 6; ++Index)
		{
			Commands.Add({EWheelMode::Drive, (Index < 3 ? Rim : -Rim) / 25.0});
		}
		return Commands;
	}

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

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRoverloomWheelFrictionTest,
	"Roverloom.WheelSpike.Friction",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRoverloomWheelFrictionTest::RunTest(const FString& Parameters)
{
	const double Dt = 1.0 / 60.0;
	const FVector Below(0.0, 0.0, -45.0);

	// The local solve: stick inside the disk, slide on its edge against the slip, continuous across the switch.
	{
		const double W00 = 3.0;
		const double W01 = 1.2;
		const double W11 = 1.0;
		bool bSliding = false;
		const FVector2D Small(0.3, -0.2);
		const FVector2D Stick = SolveContactFriction(Small, W00, W01, W11, 10.0, bSliding);
		TestFalse(TEXT("Local: small demand sticks"), bSliding);
		TestEqual(TEXT("Local: stick leaves no slip"), FVector2D(Small.X + W00 * Stick.X + W01 * Stick.Y,
			Small.Y + W01 * Stick.X + W11 * Stick.Y).Size(), 0.0, 1e-12);
		double WorstAngle = 0.0;
		bool bPositivePower = false;
		for (int32 Angle = 0; Angle < 360; Angle += 15)
		{
			const FVector2D A = 40.0 * FVector2D(FMath::Cos(FMath::DegreesToRadians(Angle)), FMath::Sin(FMath::DegreesToRadians(Angle)));
			const FVector2D F = SolveContactFriction(A, W00, W01, W11, 2.0, bSliding);
			const FVector2D U(A.X + W00 * F.X + W01 * F.Y, A.Y + W01 * F.X + W11 * F.Y);
			TestTrue(TEXT("Local: large demand slides"), bSliding);
			TestEqual(TEXT("Local: sliding force on the circle"), F.Size(), 2.0, 1e-9);
			WorstAngle = FMath::Max(WorstAngle, FMath::RadiansToDegrees(FMath::Atan2(FMath::Abs(FVector2D::CrossProduct(F, U)),
				-FVector2D::DotProduct(F, U))));
			bPositivePower |= FVector2D::DotProduct(F, U) > 0.0;
		}
		TestTrue(TEXT("Local: sliding force opposes the slip within 1e-6 deg"), WorstAngle < 1e-6);
		TestFalse(TEXT("Local: friction power never positive"), bPositivePower);
		// Continuity: scale a demand through the switch in small steps.
		FVector2D Last = SolveContactFriction(FVector2D::ZeroVector, W00, W01, W11, 2.0, bSliding);
		double LargestJump = 0.0;
		for (int32 Step = 1; Step <= 2000; ++Step)
		{
			const FVector2D F = SolveContactFriction(FVector2D(0.006, 0.004) * Step, W00, W01, W11, 2.0, bSliding);
			LargestJump = FMath::Max(LargestJump, (F - Last).Size());
			Last = F;
		}
		TestTrue(TEXT("Local: force changes continuously through the switch"), LargestJump < 0.01);
	}

	// One-direction and diagonal sliding, on a locked body and on a yaw-free body with an offset contact.
	for (const double YawInertia : {0.0, 2.0e6})
	{
		FTestRig Rig(Mass, 0.3, 0.0, {FVector(60.0, -40.0, -45.0)}, YawInertia);
		Rig.Body.LinearVelocity = FVector(30.0, 40.0, 0.0);
		double WorstAngle = 0.0;
		double LargestPower = -1.0e30;
		bool bSlid = false;
		for (int32 Index = 0; Index < 30; ++Index)
		{
			const TArray<FWheelResult> Out = Rig.Step(All(1, EWheelMode::Brake), Dt);
			if (Out[0].bSaturated)
			{
				bSlid = true;
				WorstAngle = FMath::Max(WorstAngle, SlideAngleDeg(Out[0]));
				TestEqual(TEXT("Diagonal: sliding force is mu Fz"), FMath::Sqrt(FMath::Square(Out[0].LongForce) + FMath::Square(Out[0].LatForce)),
					Out[0].FrictionLimit, 1e-6);
			}
			LargestPower = FMath::Max(LargestPower, Out[0].FrictionPower / Out[0].FrictionLimit);
		}
		TestTrue(TEXT("Diagonal: slid"), bSlid);
		TestTrue(*FString::Printf(TEXT("Diagonal, yaw inertia %.0f: force opposes slip (worst %.2e deg)"), YawInertia, WorstAngle),
			WorstAngle < 1e-6);
		// Power over mu Fz is a speed: a sticking contact's residual slip may leave rounding above zero.
		TestTrue(TEXT("Diagonal: friction power never positive, beyond 1e-6 cm/s of slip"), LargestPower <= 1e-6);
		TestTrue(TEXT("Diagonal: stopped"), Rig.LargestContactSpeed() < 1e-6);
	}

	// Stick to slide: a sideways push rising to twice the limit. The force follows the push, then holds at mu Fz.
	{
		FTestRig Rig(Mass, 0.3, 0.0, {Below});
		const double Limit = 0.3 * Mass * Gravity;
		bool bMonotonic = true;
		double LastLat = 0.0;
		double LastSpeed = 0.0;
		int32 Switches = 0;
		bool bWasSliding = false;
		for (int32 Index = 0; Index < 120; ++Index)
		{
			const double Push = 2.0 * Limit * Index / 120.0;
			Rig.Body.ExternalForce = FVector(0.0, Push, 0.0);
			const TArray<FWheelResult> Out = Rig.Step(All(1, EWheelMode::Brake), Dt);
			Rig.Body.LinearVelocity += Dt * Rig.Body.ExternalForce * Rig.Body.InvMass;
			if (!Out[0].bSaturated)
			{
				TestEqual(TEXT("Switch: sticking force balances the push"), -Out[0].LatForce, Push, 1e-6);
			}
			bMonotonic &= -Out[0].LatForce >= -LastLat - 1e-6 && Rig.Body.LinearVelocity.Y >= LastSpeed - 1e-9;
			Switches += Out[0].bSaturated != bWasSliding ? 1 : 0;
			bWasSliding = Out[0].bSaturated;
			LastLat = Out[0].LatForce;
			LastSpeed = Rig.Body.LinearVelocity.Y;
		}
		TestTrue(TEXT("Switch: force and speed rise without oscillating"), bMonotonic);
		TestEqual(TEXT("Switch: one change from stick to slide"), Switches, 1);
		TestEqual(TEXT("Switch: sliding force is mu Fz"), -LastLat, Limit, 1e-6);
	}

	// Wheel spin in the slip: a coasting wheel spinning under a still body pushes it forward and slows, conserving
	// M v + I w / R, and losing energy, until it rolls.
	{
		FTestRig Rig(Mass, 0.6, 0.0, {Below});
		Rig.Spins[0] = 4.0;
		const double R = Rig.Params.RadiusCm;
		const double I = Rig.Params.InertiaKgCm2;
		const double Momentum = I * 4.0 / R;
		double Energy = 0.5 * I * 16.0;
		bool bEnergyFalls = true;
		const TArray<FWheelResult> First = Rig.Step(All(1, EWheelMode::Coast), Dt);
		TestTrue(TEXT("Spin: first step slides"), First[0].bSaturated);
		TestTrue(TEXT("Spin: pushes the body forward"), First[0].LongForce > 0.0);
		for (int32 Index = 0; Index < 30; ++Index)
		{
			const double Now = 0.5 * Mass * Rig.Body.LinearVelocity.SizeSquared() + 0.5 * I * FMath::Square(Rig.Spins[0]);
			bEnergyFalls &= Now <= Energy + 1e-6;
			Energy = Now;
			Rig.Step(All(1, EWheelMode::Coast), Dt);
		}
		TestTrue(TEXT("Spin: energy never rises without a motor"), bEnergyFalls);
		TestEqual(TEXT("Spin: momentum kept"), Mass * Rig.Body.LinearVelocity.X + I * Rig.Spins[0] / R, Momentum, 1e-6);
		TestEqual(TEXT("Spin: rolls at the end"), Rig.Spins[0] * R, Rig.Body.LinearVelocity.X, 1e-6);
	}

	// Six wheels on a free body turning in place: steady, no cycle, net force zero, friction dissipative,
	// and the same at 60 and 120 Hz.
	double SteadyYaw[2] = {};
	const double Steps[2] = {1.0 / 60.0, 1.0 / 120.0};
	for (int32 Case = 0; Case < 2; ++Case)
	{
		FTestRig Rig = SixWheelRig();
		const TArray<FWheelCommand> Commands = TurnInPlace(28.178);
		const int32 Count = FMath::RoundToInt(10.0 / Steps[Case]);
		TArray<double> Yaw;
		double WorstAngle = 0.0;
		double LargestPower = -1.0e30;
		double LargestNet = 0.0;
		bool bConverged = true;
		for (int32 Index = 0; Index < Count; ++Index)
		{
			FSolveStats Stats;
			const TArray<FWheelResult> Out = Rig.Step(Commands, Steps[Case], &Stats);
			FVector Net = FVector::ZeroVector;
			for (int32 Wheel = 0; Wheel < 6; ++Wheel)
			{
				if (Out[Wheel].bSaturated)
				{
					WorstAngle = FMath::Max(WorstAngle, SlideAngleDeg(Out[Wheel]));
				}
				LargestPower = FMath::Max(LargestPower, Out[Wheel].FrictionPower / Out[Wheel].FrictionLimit);
				Net += FVector(Out[Wheel].LongForce, Out[Wheel].LatForce, 0.0);
			}
			if (Index >= Count / 2)
			{
				LargestNet = FMath::Max(LargestNet, Net.Size());
				bConverged &= Stats.bConverged;
			}
			Yaw.Add(FMath::RadiansToDegrees(Rig.Body.AngularVelocity.Z));
		}
		const int32 Tail = FMath::RoundToInt(1.0 / Steps[Case]);
		double Least = Yaw.Last();
		double Most = Yaw.Last();
		for (int32 Index = Yaw.Num() - Tail; Index < Yaw.Num(); ++Index)
		{
			Least = FMath::Min(Least, Yaw[Index]);
			Most = FMath::Max(Most, Yaw[Index]);
		}
		SteadyYaw[Case] = Yaw.Last();
		AddInfo(FString::Printf(TEXT("Six-wheel turn at %.0f Hz: yaw rate %.4f deg/s, last-second range %.3e, sliding angle %.2e deg, "
			"max friction power over mu Fz %.3e cm/s, max net force %.3e"), 1.0 / Steps[Case], SteadyYaw[Case], Most - Least, WorstAngle, LargestPower,
			LargestNet));
		TestTrue(TEXT("Six-wheel turn: turns the commanded way"), SteadyYaw[Case] > 0.0);
		TestTrue(TEXT("Six-wheel turn: steady, with no cycle in the last second"), Most - Least < 1e-6);
		TestTrue(TEXT("Six-wheel turn: sliding force opposes slip"), WorstAngle < 1e-6);
		TestTrue(TEXT("Six-wheel turn: friction power never positive, beyond 1e-6 cm/s of slip"), LargestPower <= 1e-6);
		TestTrue(TEXT("Six-wheel turn: no net force in steady turning"), LargestNet < 1e-3 * 853.5 * Gravity);
		TestTrue(TEXT("Six-wheel turn: no net yaw torque at steady rate"), FMath::Abs(Rig.Body.AngularVelocity.Z - FMath::DegreesToRadians(Yaw[Yaw.Num() - 2])) < 1e-9);
	}
	TestTrue(TEXT("Six-wheel turn: 60 and 120 Hz within 1%"), FMath::Abs(SteadyYaw[1] / SteadyYaw[0] - 1.0) < 0.01);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRoverloomWheelSolverTest,
	"Roverloom.WheelSpike.Solver",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRoverloomWheelSolverTest::RunTest(const FString& Parameters)
{
	const double Dt = 1.0 / 60.0;

	// Warm start: a start outside the circle is clamped, and a wheel out of contact ignores its start.
	{
		FTestRig Rig(Mass, 0.3, 0.0, {FVector(0.0, 0.0, -45.0), FVector(50.0, 0.0, -45.0)});
		Rig.Contacts[1].bHit = false;
		TArray<FWheelResult> Out;
		FSolveStats Stats;
		const TArray<FVector2D> Start = {FVector2D(1.0e9, 0.0), FVector2D(5.0e4, 5.0e4)};
		TArray<double> Spins = Rig.Spins;
		SolveWheels(Rig.Params, Rig.Body, Rig.Contacts, All(2, EWheelMode::Brake), Dt, Spins, Out, Stats, FSolverOptions(), Start);
		TestTrue(TEXT("Warm start: result inside the circle"),
			FVector2D(Out[0].LongForce, Out[0].LatForce).Size() <= Out[0].FrictionLimit * (1.0 + 1e-12));
		TestEqual(TEXT("Warm start: body at rest keeps zero traction"), Out[0].LongForce, 0.0, 1e-6);
		TestEqual(TEXT("Warm start: no force on a wheel out of contact"), Out[1].LongForce + Out[1].LatForce, 0.0);
	}

	// Same state, different orders and pass counts: wheel forces may differ, net force and torque must not.
	{
		FTestRig Rig = SixWheelRig();
		const TArray<FWheelCommand> Commands = TurnInPlace(28.178);
		for (int32 Index = 0; Index < 600; ++Index)
		{
			Rig.Step(Commands, Dt);
		}
		struct FCase
		{
			ESolveOrder Order;
			int32 Passes;
		};
		const FCase Cases[] = {{ESolveOrder::Forward, 200}, {ESolveOrder::Forward, 20000}, {ESolveOrder::Reverse, 20000},
			{ESolveOrder::Alternate, 20000}, {ESolveOrder::Shuffle, 20000}};
		TArray<FSolveStats> All5;
		TArray<TArray<FWheelResult>> Forces;
		for (const FCase& Case : Cases)
		{
			FSolverOptions Options;
			Options.Order = Case.Order;
			Options.MaxPasses = Case.Passes;
			Options.ToleranceCmps = 1e-11;
			TArray<double> Spins = Rig.Spins;
			TArray<FWheelResult> Out;
			FSolveStats Stats;
			SolveWheels(Rig.Params, Rig.Body, Rig.Contacts, Commands, Dt, Spins, Out, Stats, Options);
			All5.Add(Stats);
			Forces.Add(Out);
		}
		double NetForce = 0.0;
		double NetTorque = 0.0;
		double WheelForce = 0.0;
		for (int32 Case = 1; Case < All5.Num(); ++Case)
		{
			NetForce = FMath::Max(NetForce, (All5[Case].NetForce - All5[1].NetForce).Size());
			NetTorque = FMath::Max(NetTorque, (All5[Case].NetTorque - All5[1].NetTorque).Size());
			for (int32 Wheel = 0; Wheel < 6; ++Wheel)
			{
				WheelForce = FMath::Max(WheelForce, FMath::Abs(Forces[Case][Wheel].LatForce - Forces[1][Wheel].LatForce));
			}
			TestTrue(TEXT("Orders: natural residual small with many passes"), All5[Case].NaturalResidual < 1e-6);
		}
		AddInfo(FString::Printf(TEXT("Turn state: 200 passes residual %.3e (passes %d); orders differ by net force %.3e, net torque %.3e, "
			"single-wheel lateral force %.3e"), All5[0].NaturalResidual, All5[0].Iterations, NetForce, NetTorque, WheelForce));
		TestTrue(TEXT("Orders: same net force"), NetForce < 1e-3);
		TestTrue(TEXT("Orders: same net torque"), NetTorque < 1e-1);
	}
	return true;
}

#endif

