// Contact solver research, C++ port of scripts/contact_solver. Not gated; no scoring; no engine code.
// See docs/results/unreal-wheel-model/solver-cpp.md. Units: cm, kg, s.
//
// One wheel-model step in generalized velocities q (12): body v (3), body w (3), six wheel spins.
// Every solver here works on fixed-size arrays and allocates nothing on the heap.
#pragma once

#include <array>
#include <cstdint>

namespace wheel_solver
{
	constexpr int Wheels = 6;
	constexpr int NQ = 12; // generalized velocities
	constexpr int NX = 18; // per wheel: F_f, F_l, tau

	using VecQ = std::array<double, NQ>;
	using VecX = std::array<double, NX>;
	using Mat3 = std::array<std::array<double, 3>, 3>;

	enum Mode : int { Drive = 0, Brake = 1, Coast = 2 };

	// A dumped solver input, as the Unreal rig writes it.
	struct Input
	{
		double Dt = 0, Radius = 0, WheelInertia = 0, Spring = 0, Damper = 0, Friction = 0, Motor = 0, Brake = 0;
		double InvMass = 0;
		Mat3 InvInertia{};
		double Com[3]{}, V[3]{}, W[3]{}, Acc[3]{}, Ext[3]{};
		struct Wheel
		{
			bool Hit = false;
			double Comp = 0, CompRate = 0, Point[3]{}, Normal[3]{}, Forward[3]{}, Lateral[3]{};
			int Mode = 0;
			double Target = 0, Spin = 0;
			double EngineLong = 0, EngineLat = 0, EngineMotor = 0, EngineBrake = 0;
		} Wheel[Wheels];
	};

	struct Problem
	{
		double Dt = 0, Radius = 0, WheelInertia = 0, Mass = 0;
		Mat3 Inertia{}, InvInertia{};
		VecQ QStar{};
		std::array<VecQ, NX> Rows{}; // 3 per wheel: contact f, contact l, motor; zero where absent
		VecX Offsets{};
		double FrictionLimit[Wheels]{}, TorqueLimit[Wheels]{};
		bool InContact[Wheels]{};
		double Forward[Wheels][3]{}, Lateral[Wheels][3]{}, ArmF[Wheels][3]{}, ArmL[Wheels][3]{};
		std::array<VecX, NX> A{}; // dt G M^-1 G^T
		VecX B{};                 // G q* - offsets
	};

	Problem Build(const Input& In);
	VecX EngineX(const Input& In);

	VecQ VelocityAfter(const Problem& P, const VecX& X);
	VecQ MassApply(const Problem& P, const VecQ& V);
	VecQ InvMassApply(const Problem& P, const VecQ& V);
	double NaturalResidual(const Problem& P, const VecX& X);

	struct Checks
	{
		double Natural = 0, StickSlip = 0, SlideAngleDeg = 0, CircleExcess = -1, TorqueExcess = -1;
		double NetForce[3]{}, NetTorque[3]{};
		VecQ Q{};
		double FrictionPower = 0, MotorPower = 0, Dissipation = 0, EnergyIdentityError = 0;
	};
	Checks Evaluate(const Problem& P, const VecX& X);

	struct Result
	{
		VecX X{};
		VecQ Q{};
		int Iterations = 0;       // PGS passes, or Newton steps for D
		int Rounds = 0, Attempts = 0;
		int FallbackPasses = 0;
		double FallbackSeconds = 0;
		double LastChange = 0;
		double Natural = 0;
		bool Stopped = false;     // Met its own stop rule or target
		bool BudgetHit = false;   // Stopped by an iteration or time budget
	};

	enum class Order { Forward, Alternate };

	struct PgsOptions
	{
		int Passes = 200;
		double Tolerance = 1e-7;    // WheelModel.cpp's last-change rule, in cm/s
		double StopNatural = 0;     // If > 0, stop on the natural residual instead, checked every 5 passes
		Order PassOrder = Order::Forward;
		const VecX* Start = nullptr;
		double Gamma = 0;           // Regularization gamma diag(A)
		double Deadline = 0;        // If > 0, a steady_clock time in seconds; checked every pass
	};
	Result Pgs(const Problem& P, const PgsOptions& O);

	// Multiplier step for dependent sticking rows.
	enum class Pseudo
	{
		JacobiCutoff,     // As the Python prototype: eigenvalues below Cutoff times the largest are dropped
		JacobiRefined,    // The same rank decision, then two refinement passes inside the kept eigenspace
		TikhonovRefined,  // (S + delta I) solves with iterative refinement: converges to the pseudo-inverse
	};

	struct DOptions
	{
		double PredictorEps = 1e-5;
		double Target = 1e-8;
		int MaxRounds = 20;
		Pseudo Multipliers = Pseudo::JacobiCutoff;
		double Cutoff = 1e-10;       // Rank decision for the Jacobi kinds, relative to the largest eigenvalue
		bool FloorStiffSlip = false; // Floor |z| in a sliding term's Hessian, with a residual line search
		double StiffSlipFloor = 1e-6; // That floor, in cm/s (rad/s times R for motors)
		bool Fallback = true;
		int FallbackPasses = 5000;
		int MaxNewtonTotal = 1 << 30; // Budget on Newton steps across every stage
		double MaxSeconds = 1e30;     // Budget on wall time, checked every Newton step and fallback pass; past it
		                              // the best result so far is returned
	};
	Result D(const Problem& P, const DOptions& O);

	// Heap allocations seen by the benchmark's counting operator new, if it installs one.
	extern std::uint64_t Allocations;
}
