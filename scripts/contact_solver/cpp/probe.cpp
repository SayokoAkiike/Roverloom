// Diagnostics for states where improved D stalls above its target. Not gated.
//
//   probe <states.txt> <line numbers file> <out.txt>
//
// For each listed state it breaks the natural residual of several answers down by wheel and by part, so the source
// of a stall shows: a sticking contact's slip, a sliding contact's direction, or a motor's spin error.
#include "wheel_solver.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace wheel_solver;

namespace
{
	bool ReadState(const std::string& Line, Input& I)
	{
		std::istringstream S(Line);
		std::string Window;
		int Index;
		S >> Window >> Index >> I.Dt >> I.Radius >> I.WheelInertia >> I.Spring >> I.Damper >> I.Friction >> I.Motor >> I.Brake >>
			I.InvMass;
		for (auto& R : I.InvInertia)
			for (double& V : R) S >> V;
		for (double* V : {I.Com, I.V, I.W, I.Acc, I.Ext})
			for (int K = 0; K < 3; ++K) S >> V[K];
		for (auto& W : I.Wheel)
		{
			double Hit, Mode;
			S >> Hit >> W.Comp >> W.CompRate;
			for (double* V : {W.Point, W.Normal, W.Forward, W.Lateral})
				for (int K = 0; K < 3; ++K) S >> V[K];
			S >> Mode >> W.Target >> W.Spin >> W.EngineLong >> W.EngineLat >> W.EngineMotor >> W.EngineBrake;
			W.Hit = Hit != 0;
			W.Mode = static_cast<int>(Mode);
		}
		return static_cast<bool>(S);
	}

	// Jacobi eigen-decomposition, local copy for the probe.
	void Eigen(std::vector<std::vector<double>> M, std::vector<double>& Values, std::vector<std::vector<double>>& Vectors)
	{
		const int N = static_cast<int>(M.size());
		Vectors.assign(N, std::vector<double>(N, 0.0));
		for (int I = 0; I < N; ++I) Vectors[I][I] = 1;
		for (int Sweep = 0; Sweep < 100; ++Sweep)
			for (int Pp = 0; Pp < N; ++Pp)
				for (int Qq = Pp + 1; Qq < N; ++Qq)
				{
					if (std::abs(M[Pp][Qq]) < 1e-300) continue;
					const double Theta = (M[Qq][Qq] - M[Pp][Pp]) / (2 * M[Pp][Qq]);
					const double T = std::copysign(1.0, Theta) / (std::abs(Theta) + std::sqrt(Theta * Theta + 1));
					const double C = 1 / std::sqrt(T * T + 1), S = T * C;
					for (int K = 0; K < N; ++K)
					{
						const double A = M[K][Pp], B = M[K][Qq];
						M[K][Pp] = C * A - S * B;
						M[K][Qq] = S * A + C * B;
					}
					for (int K = 0; K < N; ++K)
					{
						const double A = M[Pp][K], B = M[Qq][K];
						M[Pp][K] = C * A - S * B;
						M[Qq][K] = S * A + C * B;
					}
					for (int K = 0; K < N; ++K)
					{
						const double A = Vectors[K][Pp], B = Vectors[K][Qq];
						Vectors[K][Pp] = C * A - S * B;
						Vectors[K][Qq] = S * A + C * B;
					}
				}
		Values.resize(N);
		for (int I = 0; I < N; ++I) Values[I] = M[I][I];
	}

	// Are the sticking and holding constraints at D's answer consistent? Rows: each sticking contact (2) and holding
	// motor (1). With S = G M^-1 G^T, the least-squares velocity change that zeroes their slips needs, along each
	// eigenvector v of S with eigenvalue l, a multiplier step (v . z) / l. A nearly zero l with v . z not zero means
	// the constraints cannot all hold: the exact optimum would need a huge internal force along v.
	void Consistency(std::FILE* Out, const Problem& P, const VecX& X, const VecQ& Q)
	{
		std::vector<VecQ> Rows;
		std::vector<double> Z;
		for (int I = 0; I < Wheels; ++I)
		{
			if (P.InContact[I] && P.FrictionLimit[I] > 0 && std::hypot(X[3 * I], X[3 * I + 1]) < P.FrictionLimit[I] * (1 - 1e-9))
				for (int K = 0; K < 2; ++K)
				{
					Rows.push_back(P.Rows[3 * I + K]);
					double S = -P.Offsets[3 * I + K];
					for (int C = 0; C < NQ; ++C) S += P.Rows[3 * I + K][C] * Q[C];
					Z.push_back(S);
				}
			if (P.TorqueLimit[I] > 0 && std::abs(X[3 * I + 2]) < P.TorqueLimit[I] * (1 - 1e-9))
			{
				Rows.push_back(P.Rows[3 * I + 2]);
				double S = -P.Offsets[3 * I + 2];
				for (int C = 0; C < NQ; ++C) S += P.Rows[3 * I + 2][C] * Q[C];
				Z.push_back(S);
			}
		}
		const int N = static_cast<int>(Rows.size());
		std::vector<std::vector<double>> S(N, std::vector<double>(N));
		for (int I = 0; I < N; ++I)
		{
			const VecQ Mi = InvMassApply(P, Rows[I]);
			for (int J = 0; J < N; ++J)
			{
				double V = 0;
				for (int C = 0; C < NQ; ++C) V += Rows[J][C] * Mi[C];
				S[J][I] = V;
			}
		}
		std::vector<double> Values;
		std::vector<std::vector<double>> Vectors;
		Eigen(S, Values, Vectors);
		double Top = 0;
		for (double V : Values) Top = std::max(Top, std::abs(V));
		std::fprintf(Out, "  held rows %d on %d freedoms; eigenvalues of S over the largest, with |v . z| (cm/s or rad/s):", N, NQ);
		std::vector<int> Order(N);
		for (int I = 0; I < N; ++I) Order[I] = I;
		std::sort(Order.begin(), Order.end(), [&](int A, int B) { return Values[A] < Values[B]; });
		for (int K : Order)
		{
			double Proj = 0;
			for (int I = 0; I < N; ++I) Proj += Vectors[I][K] * Z[I];
			std::fprintf(Out, " [%.1e %.1e]", Values[K] / Top, std::abs(Proj));
		}
		std::fprintf(Out, "\n");
		double Null = 0, Range = 0;
		for (int K = 0; K < N; ++K)
		{
			double Proj = 0;
			for (int I = 0; I < N; ++I) Proj += Vectors[I][K] * Z[I];
			(Values[K] <= 1e-12 * Top ? Null : Range) = std::max(Values[K] <= 1e-12 * Top ? Null : Range, std::abs(Proj));
		}
		std::fprintf(Out, "  SUMMARY held %d null %d max|v.z| on null %.3e on the rest %.3e\n", N,
			static_cast<int>(std::count_if(Values.begin(), Values.end(), [&](double V) { return V <= 1e-12 * Top; })), Null, Range);
	}

	// Per wheel: the force part and torque part of the natural residual, with the state that produced each.
	void Breakdown(std::FILE* Out, const char* Label, const Problem& P, const VecX& X)
	{
		VecX W{};
		for (int R = 0; R < NX; ++R)
		{
			double S = P.B[R];
			for (int C = 0; C < NX; ++C) S += P.A[R][C] * X[C];
			W[R] = S;
		}
		std::fprintf(Out, "  %s natural %.3e\n", Label, NaturalResidual(P, X));
		for (int I = 0; I < Wheels; ++I)
		{
			const double Limit = P.FrictionLimit[I], L = P.TorqueLimit[I];
			const double F = std::hypot(X[3 * I], X[3 * I + 1]);
			const double U = std::hypot(W[3 * I], W[3 * I + 1]);
			double Force = 0, Angle = 0;
			if (P.InContact[I] && Limit > 0)
			{
				const double Rho = 1.0 / std::max(P.A[3 * I][3 * I], P.A[3 * I + 1][3 * I + 1]);
				double Tx = X[3 * I] - Rho * W[3 * I], Ty = X[3 * I + 1] - Rho * W[3 * I + 1];
				const double Ts = std::hypot(Tx, Ty);
				if (Ts > Limit)
				{
					Tx *= Limit / Ts;
					Ty *= Limit / Ts;
				}
				Force = std::hypot(X[3 * I] - Tx, X[3 * I + 1] - Ty) / Limit;
				if (U > 0 && F > 0)
					Angle = std::atan2(std::abs(X[3 * I] * W[3 * I + 1] - X[3 * I + 1] * W[3 * I]),
						-(X[3 * I] * W[3 * I] + X[3 * I + 1] * W[3 * I + 1]));
			}
			double Torque = 0;
			if (L > 0)
			{
				const double Rho = 1.0 / P.A[3 * I + 2][3 * I + 2];
				const double Trial = std::min(std::max(X[3 * I + 2] - Rho * W[3 * I + 2], -L), L);
				Torque = std::abs(X[3 * I + 2] - Trial) / L;
			}
			std::fprintf(Out,
				"    wheel %d: |F|/limit %.12f |u| %.3e angle %.3e rad -> force part %.3e | tau/L %.12f s %.3e -> torque part %.3e\n",
				I, Limit > 0 ? F / Limit : 0.0, U, Angle, Force, L > 0 ? X[3 * I + 2] / L : 0.0, W[3 * I + 2], Torque);
		}
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 4) return 2;
	std::vector<std::string> Lines;
	{
		std::ifstream S(Argv[1]);
		for (std::string L; std::getline(S, L);) Lines.push_back(L);
	}
	std::vector<int> Chosen;
	{
		std::ifstream S(Argv[2]);
		for (int K; S >> K;) Chosen.push_back(K);
	}
	std::FILE* Out = std::fopen(Argv[3], "w");
	for (int K : Chosen)
	{
		Input In;
		ReadState(Lines[K], In);
		const Problem P = Build(In);
		std::fprintf(Out, "state %d: %s\n", K, Lines[K].substr(0, Lines[K].find(' ', Lines[K].find(' ') + 1)).c_str());
		DOptions O;
		O.FloorStiffSlip = true;
		O.Fallback = false;
		Trace T;
		O.History = &T;
		const Result Dr = D(P, O);
		Breakdown(Out, "improved D", P, Dr.X);
		std::fprintf(Out, "  last partition: %d steps, converged %d; step norm, alpha, merit:", T.Steps, T.Converged ? 1 : 0);
		for (int K = std::max(0, T.Steps - 6); K < T.Steps; ++K)
			std::fprintf(Out, " [%.2e %.2e %.2e]", T.StepNorm[K], T.Alpha[K], T.Merit[K]);
		std::fprintf(Out, "\n");
		// Variants of the stop, to see which part stalls.
		struct Variant { const char* Name; bool Full; int PerPartition; bool Floor; } Variants[] = {
			{"full-step convergence test", true, 50, true}, {"200 Newton steps per partition", false, 200, true},
			{"no floor (as Python)", false, 50, false}};
		for (const auto& V : Variants)
		{
			DOptions Vo;
			Vo.Fallback = false;
			Vo.FloorStiffSlip = V.Floor;
			Vo.ConvergeOnFullStep = V.Full;
			Vo.MaxNewtonPerPartition = V.PerPartition;
			std::fprintf(Out, "  variant %-32s natural %.3e\n", V.Name, D(P, Vo).Natural);
		}
		Consistency(Out, P, Dr.X, Dr.Q);
		// A long alternating PGS from D's answer: does anything get lower?
		PgsOptions Po;
		Po.PassOrder = Order::Alternate;
		Po.Start = &Dr.X;
		Po.Passes = 50000;
		Po.StopNatural = 1e-13;
		const Result Pg = Pgs(P, Po);
		Breakdown(Out, "PGS 50,000 from D", P, Pg.X);
		double Dq = 0;
		for (int J = 0; J < NQ; ++J) Dq = std::max(Dq, std::abs(Pg.Q[J] - Dr.Q[J]));
		std::fprintf(Out, "  passes %d; largest velocity difference D vs PGS %.3e\n", Pg.Iterations, Dq);
		// Rounding check: the residual of D's answer recomputed after perturbing its forces by one ulp each.
		VecX Bumped = Dr.X;
		for (double& V : Bumped) V = std::nextafter(V, V > 0 ? 1e300 : -1e300);
		std::fprintf(Out, "  natural after one-ulp bump of every force %.3e\n", NaturalResidual(P, Bumped));
	}
	std::fclose(Out);
	return 0;
}
