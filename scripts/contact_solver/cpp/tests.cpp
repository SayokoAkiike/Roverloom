// Unit tests of the C++ solvers on synthetic six-wheel states, mirroring test_contact_solver.py. Not gated.
#include "wheel_solver.h"

#include <cmath>
#include <cstdio>

using namespace wheel_solver;

namespace
{
	int Failures = 0;

	void Check(bool Ok, const char* What, double Value)
	{
		std::printf("%s %s (%.3e)\n", Ok ? "ok  " : "FAIL", What, Value);
		Failures += Ok ? 0 : 1;
	}

	// pathfinder_6w's box on flat ground, every wheel at static compression.
	Input SixWheel(double YawRateDegps, double TurnDegps, double Vx, double Vy, int Mode, double Friction)
	{
		const double M = 853.5, G = 371.0;
		Input In;
		In.Dt = 1.0 / 60;
		In.Radius = 25;
		In.WheelInertia = 3750;
		In.Spring = M * G / 6 / 5;
		In.Damper = 0;
		In.Friction = Friction;
		In.Motor = 6e5;
		In.Brake = 2e6;
		In.InvMass = 1 / M;
		In.InvInertia = {{{12 / (M * (150 * 150 + 40 * 40)), 0, 0}, {0, 12 / (M * (200 * 200 + 40 * 40)), 0},
			{0, 0, 12 / (M * (200 * 200 + 150 * 150))}}};
		In.V[0] = Vx;
		In.V[1] = Vy;
		In.W[2] = YawRateDegps * M_PI / 180;
		In.Acc[2] = -G;
		const double Rim = TurnDegps * M_PI / 180 * 103.7;
		int I = 0;
		for (double Y : {-103.7, 103.7})
			for (double X : {97.6, 0.0, -97.6})
			{
				auto& W = In.Wheel[I++];
				W.Hit = true;
				W.Comp = 5;
				W.Point[0] = X;
				W.Point[1] = Y;
				W.Point[2] = -45;
				W.Normal[2] = 1;
				W.Forward[0] = 1;
				W.Lateral[1] = 1;
				W.Mode = Mode;
				W.Target = W.Spin = (Y < 0 ? Rim : -Rim) / 25;
			}
		return In;
	}
}

int main()
{
	const Input Cases[] = {SixWheel(18.98, 28.178, 0, 0, Drive, 0.6), SixWheel(0, 0, 30, 40, Brake, 0.3),
		SixWheel(0, 0, 20, 0, Coast, 0.6), SixWheel(0, 0, 0, 0, Drive, 0.6)};
	const char* Names[] = {"turn", "diagonal slide", "coast", "rest"};
	for (int C = 0; C < 4; ++C)
	{
		const Problem P = Build(Cases[C]);
		for (Pseudo Kind : {Pseudo::JacobiCutoff, Pseudo::TikhonovRefined})
		{
			DOptions O;
			O.Multipliers = Kind;
			O.Fallback = false;
			const Result R = D(P, O);
			const Checks K = Evaluate(P, R.X);
			char Label[96];
			std::snprintf(Label, sizeof Label, "%s, %s: D alone reaches 1e-12", Names[C], Kind == Pseudo::JacobiCutoff ? "Jacobi" : "Tikhonov");
			Check(R.Natural < 1e-12, Label, R.Natural);
			std::snprintf(Label, sizeof Label, "%s: circle and torque limits hold", Names[C]);
			Check(K.CircleExcess <= 1e-12 && K.TorqueExcess <= 1e-12, Label, std::max(K.CircleExcess, K.TorqueExcess));
			std::snprintf(Label, sizeof Label, "%s: friction does no positive work", Names[C]);
			Check(K.FrictionPower <= 1e-6, Label, K.FrictionPower);
			std::snprintf(Label, sizeof Label, "%s: energy identity", Names[C]);
			Check(std::abs(K.EnergyIdentityError) < 1e-6, Label, K.EnergyIdentityError);
		}
		// D and a converged alternating PGS give the same motion, whatever their forces.
		PgsOptions Po;
		Po.PassOrder = Order::Alternate;
		Po.Passes = 20000;
		Po.StopNatural = 1e-11;
		const Result Pg = Pgs(P, Po);
		const Result Dr = D(P, DOptions{});
		double Gap = 0;
		for (int K = 0; K < NQ; ++K) Gap = std::max(Gap, std::abs(Pg.Q[K] - Dr.Q[K]));
		char Label[96];
		std::snprintf(Label, sizeof Label, "%s: D and PGS agree on velocities", Names[C]);
		Check(Gap < 1e-6, Label, Gap);
	}
	// Sliding force opposes slip.
	{
		const Problem P = Build(SixWheel(0, 0, 30, 40, Brake, 0.3));
		const Checks K = Evaluate(P, D(P, DOptions{}).X);
		Check(K.SlideAngleDeg < 1e-9, "diagonal slide: force opposes slip", K.SlideAngleDeg);
	}
	std::printf("%d failures\n", Failures);
	return Failures ? 1 : 0;
}
