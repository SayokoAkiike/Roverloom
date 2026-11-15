// Short trajectories of the six-wheel rig in C++, mirroring scripts/contact_solver/simulate.py step for step. Not gated.
//
//   traj <out dir> [--round-f32]
//
// Same rig, rays to a plane, scenarios, command schedule, and Chaos's step order as the Python stand-in. Writes one CSV
// per method, scenario, and rate, with every step's state, contact states, net wrench, energy, residual, and solve time.
// --round-f32 rounds each contact point to the nearest 32-bit float before the solve, as a test of single-precision
// contact points (docs/results/unreal-wheel-model/stall-geometry.md). Without it, nothing changes.
#include "wheel_solver.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <string>

using namespace wheel_solver;

namespace
{
	constexpr double Mass = 853.5, Gravity = 371.0, Radius = 25.0, Rest = 30.0, Settle = 0.5;
	const double Spring = Mass * Gravity / 6 / 5.0;
	const double Damper = 2 * 0.7 * std::sqrt(Spring * Mass / 6);
	const double Principal[3] = {Mass / 12 * (150.0 * 150 + 40.0 * 40), Mass / 12 * (200.0 * 200 + 40.0 * 40),
		Mass / 12 * (200.0 * 200 + 150.0 * 150)};
	const double Mounts[6][3] = {{97.6, -103.7, -20}, {0, -103.7, -20}, {-97.6, -103.7, -20}, {97.6, 103.7, -20},
		{0, 103.7, -20}, {-97.6, 103.7, -20}};

	struct Scenario
	{
		const char* Name;
		double Slope, Forward, Yaw, Seconds, Friction, BrakeAt, StartZ;
	};
	const Scenario Scenarios[] = {
		{"straight", 0, 50, 0, 3, 0.6, -1, 70},
		{"turn", 0, 0, 28.178, 4, 0.6, -1, 70},
		{"climb10", 10, 50, 0, 3, 0.6, -1, 70},
		{"hold10", 10, 0, 0, 3, 0.6, -1, 70},
		{"stop", 0, 50, 0, 3, 0.2, 1.5, 70},
		{"drop", 0, 0, 0, 2, 0.6, -1, 90},
	};

	void Cross(const double* A, const double* B, double* Out)
	{
		const double X = A[1] * B[2] - A[2] * B[1], Y = A[2] * B[0] - A[0] * B[2], Z = A[0] * B[1] - A[1] * B[0];
		Out[0] = X;
		Out[1] = Y;
		Out[2] = Z;
	}
	double Dot(const double* A, const double* B) { return A[0] * B[0] + A[1] * B[1] + A[2] * B[2]; }

	void Rotate(const double Q[4], const double V[3], double Out[3])
	{
		const double U[3] = {Q[1], Q[2], Q[3]};
		double T[3], C[3];
		Cross(U, V, T);
		for (double& X : T) X *= 2;
		Cross(U, T, C);
		for (int K = 0; K < 3; ++K) Out[K] = V[K] + Q[0] * T[K] + C[K];
	}

	void Integrate(double Q[4], const double W[3], double Dt)
	{
		const double D[4] = {-W[0] * Q[1] - W[1] * Q[2] - W[2] * Q[3], W[0] * Q[0] + W[1] * Q[3] - W[2] * Q[2],
			W[1] * Q[0] + W[2] * Q[1] - W[0] * Q[3], W[2] * Q[0] + W[0] * Q[2] - W[1] * Q[1]};
		double N = 0;
		for (int K = 0; K < 4; ++K)
		{
			Q[K] += 0.5 * Dt * D[K];
			N += Q[K] * Q[K];
		}
		N = std::sqrt(N);
		for (int K = 0; K < 4; ++K) Q[K] /= N;
	}

	// World inertia (Inverse false) or its inverse (true), from the principal values.
	Mat3 WorldInertia(const double Q[4], bool Inverse)
	{
		double Axes[3][3];
		const double E[3][3] = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};
		for (int A = 0; A < 3; ++A) Rotate(Q, E[A], Axes[A]);
		Mat3 M{};
		for (int R = 0; R < 3; ++R)
			for (int C = 0; C < 3; ++C)
				for (int A = 0; A < 3; ++A)
					M[R][C] += Axes[A][R] * Axes[A][C] * (Inverse ? 1.0 / Principal[A] : Principal[A]);
		return M;
	}

	struct Method
	{
		const char* Name;
		DOptions D;
		bool Pgs;
	};

	void Run(const Method& M, const Scenario& S, int Rate, const std::string& Dir, bool RoundF32)
	{
		const double Dt = 1.0 / Rate;
		const double Slope = S.Slope * M_PI / 180;
		const double G[3] = {-Gravity * std::sin(Slope), 0.0, -Gravity * std::cos(Slope)};
		double Pos[3] = {0, 0, S.StartZ}, Orient[4] = {1, 0, 0, 0}, Vel[3] = {0, 0, 0}, Omega[3] = {0, 0, 0}, Spins[6] = {};
		const std::string Path = Dir + "/" + M.Name + "_" + S.Name + "_" + std::to_string(Rate) + ".csv";
		std::FILE* Out = std::fopen(Path.c_str(), "w");
		std::fprintf(Out, "t,x,y,z,qw,qx,qy,qz,vx,vy,vz,wx,wy,wz,s0,s1,s2,s3,s4,s5,c0,c1,c2,c3,c4,c5,fx,fy,fz,tx,ty,tz,"
			"energy,motor_work,identity_error,natural,solve_us,budget_hit\n");
		double MotorWork = 0;
		const int Steps = static_cast<int>(std::lround(S.Seconds * Rate));
		for (int Step = 0; Step < Steps; ++Step)
		{
			const double T = Step * Dt;
			const bool Driving = T >= Settle;
			const double Turn = (Driving ? S.Yaw : 0.0) * M_PI / 180 * 103.7;
			const double Forward = Driving ? S.Forward : 0.0;
			const bool Braking = S.BrakeAt >= 0 && T >= S.BrakeAt;
			double Up[3], FwdAxis[3], RightAxis[3];
			const double Ez[3] = {0, 0, 1}, Ex[3] = {1, 0, 0}, Ey[3] = {0, 1, 0};
			Rotate(Orient, Ez, Up);
			Rotate(Orient, Ex, FwdAxis);
			Rotate(Orient, Ey, RightAxis);
			Input In;
			In.Dt = Dt;
			In.Radius = Radius;
			In.WheelInertia = 0.4 * 15 * Radius * Radius;
			In.Spring = Spring;
			In.Damper = Damper;
			In.Friction = S.Friction;
			In.Motor = 6e5;
			In.Brake = 2e6;
			In.InvMass = 1 / Mass;
			In.InvInertia = WorldInertia(Orient, true);
			for (int K = 0; K < 3; ++K)
			{
				In.Com[K] = Pos[K];
				In.V[K] = Vel[K];
				In.W[K] = Omega[K];
				In.Acc[K] = G[K];
			}
			for (int I = 0; I < 6; ++I)
			{
				auto& W = In.Wheel[I];
				double Offset[3], Mp[3], Wo[3];
				Rotate(Orient, Mounts[I], Offset);
				for (int K = 0; K < 3; ++K) Mp[K] = Pos[K] + Offset[K];
				const double Reach = Rest + Radius;
				const bool Hit = Up[2] > 1e-6 && Mp[2] / Up[2] >= 0 && Mp[2] / Up[2] <= Reach;
				const double Dist = Hit ? Mp[2] / Up[2] : Reach;
				Cross(Omega, Offset, Wo);
				double VMount[3];
				for (int K = 0; K < 3; ++K)
				{
					W.Point[K] = Mp[K] - Dist * Up[K];
					if (RoundF32) W.Point[K] = static_cast<double>(static_cast<float>(W.Point[K]));
					VMount[K] = Vel[K] + Wo[K];
				}
				W.Normal[0] = 0;
				W.Normal[1] = 0;
				W.Normal[2] = 1;
				double F[3], L[3];
				const double Fd = Dot(FwdAxis, W.Normal);
				for (int K = 0; K < 3; ++K) F[K] = FwdAxis[K] - Fd * W.Normal[K];
				const double Fn = std::sqrt(Dot(F, F));
				for (double& X : F) X /= Fn;
				const double Ld = Dot(RightAxis, W.Normal);
				for (int K = 0; K < 3; ++K) L[K] = RightAxis[K] - Ld * W.Normal[K];
				const double Lf = Dot(L, F);
				for (int K = 0; K < 3; ++K) L[K] -= Lf * F[K];
				const double Ln = std::sqrt(Dot(L, L));
				for (double& X : L) X /= Ln;
				for (int K = 0; K < 3; ++K)
				{
					W.Forward[K] = F[K];
					W.Lateral[K] = L[K];
				}
				W.Hit = Hit;
				W.Comp = Reach - Dist;
				W.CompRate = -Dot(VMount, Up);
				W.Mode = Braking ? Brake : Drive;
				W.Target = Braking ? 0.0 : (I < 3 ? Forward + Turn : Forward - Turn) / Radius;
				W.Spin = Spins[I];
			}
			const Problem P = Build(In);
			const auto T0 = std::chrono::steady_clock::now();
			const Result R = M.Pgs ? Pgs(P, PgsOptions{}) : D(P, M.D);
			const double Us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - T0).count();
			const Checks C = Evaluate(P, R.X);
			MotorWork += Dt * C.MotorPower;
			int State[6];
			double Force[3] = {0, 0, 0}, Torque[3] = {0, 0, 0};
			for (int I = 0; I < 6; ++I)
			{
				const auto& W = In.Wheel[I];
				const double Fs = std::hypot(R.X[3 * I], R.X[3 * I + 1]);
				State[I] = !P.InContact[I] ? 0 : (Fs >= P.FrictionLimit[I] * (1 - 1e-6) ? 2 : 1); // 0 none, 1 stick, 2 slide
				if (!P.InContact[I]) continue;
				const double Fz = std::max(0.0, Spring * W.Comp + Damper * W.CompRate);
				double Total[3], Arm[3], Tq[3];
				for (int K = 0; K < 3; ++K)
				{
					Total[K] = Fz * W.Normal[K] + R.X[3 * I] * W.Forward[K] + R.X[3 * I + 1] * W.Lateral[K];
					Arm[K] = W.Point[K] - Pos[K];
					Force[K] += Total[K];
				}
				Cross(Arm, Total, Tq);
				for (int K = 0; K < 3; ++K) Torque[K] += Tq[K];
			}
			// Mechanical energy before the step: kinetic, gravity, springs.
			const Mat3 Iw = WorldInertia(Orient, false);
			double Energy = 0.5 * Mass * Dot(Vel, Vel) - Mass * Dot(G, Pos);
			for (int A = 0; A < 3; ++A)
				for (int B = 0; B < 3; ++B) Energy += 0.5 * Omega[A] * Iw[A][B] * Omega[B];
			for (int I = 0; I < 6; ++I)
			{
				Energy += 0.5 * In.WheelInertia * Spins[I] * Spins[I];
				if (In.Wheel[I].Hit) Energy += 0.5 * Spring * In.Wheel[I].Comp * In.Wheel[I].Comp;
			}
			const Mat3 Inv = In.InvInertia;
			for (int K = 0; K < 3; ++K) Vel[K] += Dt * (G[K] + Force[K] / Mass);
			double Dw[3];
			for (int K = 0; K < 3; ++K) Dw[K] = Dt * (Inv[K][0] * Torque[0] + Inv[K][1] * Torque[1] + Inv[K][2] * Torque[2]);
			for (int K = 0; K < 3; ++K) Omega[K] += Dw[K];
			for (int K = 0; K < 3; ++K) Pos[K] += Dt * Vel[K];
			Integrate(Orient, Omega, Dt);
			for (int I = 0; I < 6; ++I) Spins[I] = C.Q[6 + I];
			std::fprintf(Out,
				"%.6f,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,"
				"%d,%d,%d,%d,%d,%d,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.17g,%.17g,%.3e,%.3e,%.3f,%d\n",
				(Step + 1) * Dt, Pos[0], Pos[1], Pos[2], Orient[0], Orient[1], Orient[2], Orient[3], Vel[0], Vel[1], Vel[2], Omega[0],
				Omega[1], Omega[2], Spins[0], Spins[1], Spins[2], Spins[3], Spins[4], Spins[5], State[0], State[1], State[2], State[3],
				State[4], State[5], C.NetForce[0], C.NetForce[1], C.NetForce[2], C.NetTorque[0], C.NetTorque[1], C.NetTorque[2], Energy,
				MotorWork, C.EnergyIdentityError, C.Natural, Us, R.BudgetHit ? 1 : 0);
		}
		std::fclose(Out);
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 2) return 2;
	const std::string Dir = Argv[1];
	const bool RoundF32 = Argc > 2 && std::string(Argv[2]) == "--round-f32";
	DOptions Py; // As the Python prototype
	DOptions Imp = Py;
	Imp.FloorStiffSlip = true;
	DOptions ImpAlone = Imp;
	ImpAlone.Fallback = false;
	DOptions Imp1 = Imp;
	Imp1.MaxNewtonTotal = 300;
	Imp1.MaxSeconds = 1e-3;
	Imp1.FallbackPasses = 200;
	const Method Methods[] = {{"A", {}, true}, {"D_py", Py, false}, {"D_imp", Imp, false}, {"D_imp_alone", ImpAlone, false},
		{"D_imp_1ms", Imp1, false}};
	for (const Method& M : Methods)
		for (const Scenario& S : Scenarios)
			for (int Rate : {60, 120}) Run(M, S, Rate, Dir, RoundF32);
	std::printf("wrote %zu runs to %s%s\n", std::size(Methods) * std::size(Scenarios) * 2, Dir.c_str(),
		RoundF32 ? ", contact points rounded to 32-bit floats" : "");
	return 0;
}
