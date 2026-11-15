// Stall analysis for improved D, one CSV row per state. Not gated.
//
//   geom <states.txt> <out.csv>
//
// Solves every state with improved D alone (stiff-slip floor on, no fallback), as in the benchmark's D_imp_alone,
// and measures whether the sticking and holding rows at its answer are consistent, as probe.cpp does. Plan and
// results: docs/results/unreal-wheel-model/stall-geometry.md.
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
	// The states.txt layout written by scripts/contact_solver/export_states.py, as probe.cpp reads it.
	bool ReadState(const std::string& Line, std::string& Window, int& Index, Input& I)
	{
		std::istringstream S(Line);
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

	// Cyclic Jacobi eigen-decomposition of a symmetric matrix; columns of Vectors are eigenvectors.
	void Eigen(std::vector<std::vector<double>> M, std::vector<double>& Values, std::vector<std::vector<double>>& Vectors)
	{
		const int N = static_cast<int>(M.size());
		Vectors.assign(N, std::vector<double>(N, 0.0));
		for (int I = 0; I < N; ++I) Vectors[I][I] = 1;
		for (int Sweep = 0; Sweep < 100; ++Sweep)
			for (int P = 0; P < N; ++P)
				for (int Q = P + 1; Q < N; ++Q)
				{
					if (std::abs(M[P][Q]) < 1e-300) continue;
					const double Theta = (M[Q][Q] - M[P][P]) / (2 * M[P][Q]);
					const double T = std::copysign(1.0, Theta) / (std::abs(Theta) + std::sqrt(Theta * Theta + 1));
					const double C = 1 / std::sqrt(T * T + 1), S = T * C;
					for (int K = 0; K < N; ++K)
					{
						const double A = M[K][P], B = M[K][Q];
						M[K][P] = C * A - S * B;
						M[K][Q] = S * A + C * B;
					}
					for (int K = 0; K < N; ++K)
					{
						const double A = M[P][K], B = M[Q][K];
						M[P][K] = C * A - S * B;
						M[Q][K] = S * A + C * B;
					}
					for (int K = 0; K < N; ++K)
					{
						const double A = Vectors[K][P], B = Vectors[K][Q];
						Vectors[K][P] = C * A - S * B;
						Vectors[K][Q] = S * A + C * B;
					}
				}
		Values.resize(N);
		for (int I = 0; I < N; ++I) Values[I] = M[I][I];
	}

	struct Consistency
	{
		int Held = 0, Null = 0;
		double MinRatio = 1, NullSlip = 0, RestSlip = 0;
		int Wheels = 0; // Bit i: wheel i carries more than 10% of the worst null direction
	};

	// Rows held at the answer: each sticking contact (2) and holding motor (1). With S = G M^-1 G^T, a direction with
	// an eigenvalue at or below 1e-12 of the largest is dependent; slip along it, |v . z|, means no velocity satisfies
	// every held row.
	Consistency Measure(const Problem& P, const VecX& X, const VecQ& Q)
	{
		std::vector<VecQ> Rows;
		std::vector<double> Z;
		std::vector<int> Owner;
		for (int I = 0; I < Wheels; ++I)
		{
			auto Hold = [&](int R) {
				double S = -P.Offsets[R];
				for (int C = 0; C < NQ; ++C) S += P.Rows[R][C] * Q[C];
				Rows.push_back(P.Rows[R]);
				Z.push_back(S);
				Owner.push_back(I);
			};
			if (P.InContact[I] && P.FrictionLimit[I] > 0 && std::hypot(X[3 * I], X[3 * I + 1]) < P.FrictionLimit[I] * (1 - 1e-9))
			{
				Hold(3 * I);
				Hold(3 * I + 1);
			}
			if (P.TorqueLimit[I] > 0 && std::abs(X[3 * I + 2]) < P.TorqueLimit[I] * (1 - 1e-9)) Hold(3 * I + 2);
		}
		Consistency Out;
		const int N = static_cast<int>(Rows.size());
		Out.Held = N;
		if (N == 0) return Out;
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
		int Worst = -1;
		for (int K = 0; K < N; ++K)
		{
			double Proj = 0;
			for (int I = 0; I < N; ++I) Proj += Vectors[I][K] * Z[I];
			Proj = std::abs(Proj);
			if (Values[K] <= 1e-12 * Top)
			{
				++Out.Null;
				Out.MinRatio = std::min(Out.MinRatio, std::abs(Values[K]) / Top);
				if (Proj >= Out.NullSlip)
				{
					Out.NullSlip = Proj;
					Worst = K;
				}
			}
			else
				Out.RestSlip = std::max(Out.RestSlip, Proj);
		}
		if (Worst >= 0)
		{
			double Share[Wheels]{};
			for (int I = 0; I < N; ++I) Share[Owner[I]] += Vectors[I][Worst] * Vectors[I][Worst];
			for (int W = 0; W < Wheels; ++W)
				if (Share[W] > 0.1) Out.Wheels |= 1 << W;
		}
		return Out;
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 3)
	{
		std::fprintf(stderr, "usage: geom <states.txt> <out.csv>\n");
		return 2;
	}
	std::ifstream In(Argv[1]);
	std::FILE* Out = std::fopen(Argv[2], "w");
	if (!In || !Out) return 2;
	std::fprintf(Out, "line,window,index,natural,newton,budget_hit,held,null,min_ratio,null_slip,rest_slip,null_wheels");
	for (int K = 0; K < NQ; ++K) std::fprintf(Out, ",q%d", K);
	std::fprintf(Out, "\n");
	DOptions O; // Improved D alone, as D_imp_alone in bench.cpp
	O.FloorStiffSlip = true;
	O.Fallback = false;
	int Line = 0;
	for (std::string Text; std::getline(In, Text); ++Line)
	{
		std::string Window;
		int Index = 0;
		Input I;
		if (!ReadState(Text, Window, Index, I))
		{
			std::fprintf(stderr, "line %d: could not read\n", Line);
			return 1;
		}
		const Problem P = Build(I);
		const Result R = D(P, O);
		const Consistency C = Measure(P, R.X, R.Q);
		std::fprintf(Out, "%d,%s,%d,%.6e,%d,%d,%d,%d,%.6e,%.6e,%.6e,%d", Line, Window.c_str(), Index, R.Natural, R.Iterations,
			R.BudgetHit ? 1 : 0, C.Held, C.Null, C.MinRatio, C.NullSlip, C.RestSlip, C.Wheels);
		for (double V : R.Q) std::fprintf(Out, ",%.17g", V);
		std::fprintf(Out, "\n");
	}
	std::fclose(Out);
	return 0;
}
