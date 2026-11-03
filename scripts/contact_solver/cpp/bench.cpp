// Benchmark and cross-check of the C++ solvers on exported states. Not gated.
//
//   bench <states.txt> <python_d.txt> <out.csv> [repeats] [method,method,...]
//
// Each state is solved by every method in turn. Warm-started methods carry their own last answer along each
// window. Times are the median of `repeats` solves of the same state, with the clock read around the solve only.
// A counting operator new records heap allocations made during the timed solves.
#include "wheel_solver.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <map>
#include <new>
#include <sstream>
#include <string>
#include <sys/resource.h>
#include <vector>

using namespace wheel_solver;

void* operator new(std::size_t Size)
{
	++wheel_solver::Allocations;
	if (void* P = std::malloc(Size)) return P;
	throw std::bad_alloc();
}
void operator delete(void* P) noexcept { std::free(P); }
void operator delete(void* P, std::size_t) noexcept { std::free(P); }

namespace
{
	struct Row
	{
		std::string Window;
		int Index = 0;
		Input In;
	};

	bool ReadState(const std::string& Line, Row& Out)
	{
		std::istringstream S(Line);
		Input& I = Out.In;
		S >> Out.Window >> Out.Index >> I.Dt >> I.Radius >> I.WheelInertia >> I.Spring >> I.Damper >> I.Friction >> I.Motor >>
			I.Brake >> I.InvMass;
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

	struct PyAnswer
	{
		double Natural = 0, Fallback = 0, Seconds = 0;
		VecX X{};
		VecQ Q{};
	};

	bool ReadAnswer(const std::string& Line, PyAnswer& Out)
	{
		std::istringstream S(Line);
		std::string Window;
		int Index;
		S >> Window >> Index >> Out.Natural >> Out.Fallback >> Out.Seconds;
		for (double& V : Out.X) S >> V;
		for (double& V : Out.Q) S >> V;
		return static_cast<bool>(S);
	}

	double Distance3(const VecQ& A, const VecQ& B, int From)
	{
		double S = 0;
		for (int K = From; K < From + 3; ++K) S += (A[K] - B[K]) * (A[K] - B[K]);
		return std::sqrt(S);
	}

	double DistanceSpins(const VecQ& A, const VecQ& B)
	{
		double S = 0;
		for (int K = 6; K < NQ; ++K) S += (A[K] - B[K]) * (A[K] - B[K]);
		return std::sqrt(S);
	}

	// The last answer's force on this step's contact plane; zero where contact is new or lost.
	struct Memory
	{
		bool Valid = false;
		bool Contact[Wheels]{};
		double World[Wheels][3]{};
		double Tau[Wheels]{};
	};

	VecX WarmStart(const Problem& P, const Memory& M)
	{
		VecX S{};
		for (int I = 0; I < Wheels; ++I)
		{
			if (P.InContact[I] && M.Contact[I])
			{
				S[3 * I] = M.World[I][0] * P.Forward[I][0] + M.World[I][1] * P.Forward[I][1] + M.World[I][2] * P.Forward[I][2];
				S[3 * I + 1] = M.World[I][0] * P.Lateral[I][0] + M.World[I][1] * P.Lateral[I][1] + M.World[I][2] * P.Lateral[I][2];
			}
			S[3 * I + 2] = M.Tau[I];
		}
		return S;
	}

	void Remember(const Problem& P, const VecX& X, Memory& M)
	{
		M.Valid = true;
		for (int I = 0; I < Wheels; ++I)
		{
			M.Contact[I] = P.InContact[I];
			for (int K = 0; K < 3; ++K) M.World[I][K] = X[3 * I] * P.Forward[I][K] + X[3 * I + 1] * P.Lateral[I][K];
			M.Tau[I] = X[3 * I + 2];
		}
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 4)
	{
		std::fprintf(stderr, "usage: bench <states.txt> <python_d.txt> <out.csv> [repeats]\n");
		return 2;
	}
	const int Repeats = Argc > 4 ? std::atoi(Argv[4]) : 5;
	std::ifstream States(Argv[1]), Answers(Argv[2]);
	std::vector<Row> Rows;
	std::vector<PyAnswer> Py;
	for (std::string Line; std::getline(States, Line);)
	{
		Row R;
		if (ReadState(Line, R)) Rows.push_back(R);
	}
	for (std::string Line; std::getline(Answers, Line);)
	{
		PyAnswer A;
		if (ReadAnswer(Line, A)) Py.push_back(A);
	}
	if (Rows.size() != Py.size())
	{
		std::fprintf(stderr, "states %zu and answers %zu differ\n", Rows.size(), Py.size());
		return 1;
	}

	struct Method
	{
		std::string Name;
		bool Warm;
		std::function<Result(const Problem&, const VecX*)> Solve;
	};
	DOptions DPy; // As the Python prototype
	DOptions DTik = DPy;
	DTik.Multipliers = Pseudo::TikhonovRefined;
	DOptions DImp = DPy; // Improved: floor |z| in sliding terms' Hessian at 1e-6 cm/s, with a residual line search
	DImp.FloorStiffSlip = true;
	DOptions DImpAlone = DImp;
	DImpAlone.Fallback = false;
	// Bounded variants: Newton steps, wall time, and fallback passes all capped; past a cap the best answer so far
	// is returned and the result says so.
	DOptions DImp1 = DImp;
	DImp1.MaxNewtonTotal = 300;
	DImp1.MaxSeconds = 1e-3;
	DImp1.FallbackPasses = 200;
	DOptions DImp2 = DImp;
	DImp2.MaxNewtonTotal = 600;
	DImp2.MaxSeconds = 2e-3;
	DImp2.FallbackPasses = 600;
	const std::vector<Method> Methods = {
		{"A", false, [](const Problem& P, const VecX*) { return Pgs(P, PgsOptions{}); }},
		{"B", true, [](const Problem& P, const VecX* S) { PgsOptions O; O.PassOrder = Order::Alternate; O.Start = S; return Pgs(P, O); }},
		{"B_res", true, [](const Problem& P, const VecX* S) { PgsOptions O; O.PassOrder = Order::Alternate; O.Start = S; O.Passes = 2000; O.StopNatural = 1e-8; return Pgs(P, O); }},
		{"D_py", false, [&](const Problem& P, const VecX*) { return D(P, DPy); }},
		{"D_tik", false, [&](const Problem& P, const VecX*) { return D(P, DTik); }},
		{"D_imp_alone", false, [&](const Problem& P, const VecX*) { return D(P, DImpAlone); }},
		{"D_imp", false, [&](const Problem& P, const VecX*) { return D(P, DImp); }},
		{"D_imp_1ms", false, [&](const Problem& P, const VecX*) { return D(P, DImp1); }},
		{"D_imp_2ms", false, [&](const Problem& P, const VecX*) { return D(P, DImp2); }},
	};
	// Rank-decision variants, with no fallback, so that D's own result shows.
	std::vector<Method> Extra;
	for (double Cut : {1e-6, 1e-8, 1e-12})
		for (Pseudo Kind : {Pseudo::JacobiCutoff, Pseudo::JacobiRefined})
		{
			DOptions O = DPy;
			O.Fallback = false;
			O.Cutoff = Cut;
			O.Multipliers = Kind;
			char Name[48];
			std::snprintf(Name, sizeof Name, "Dalone_%s_%.0e", Kind == Pseudo::JacobiCutoff ? "cut" : "ref", Cut);
			Extra.push_back({Name, false, [O](const Problem& P, const VecX*) { return D(P, O); }});
		}
	{
		DOptions O = DPy;
		O.Fallback = false;
		O.Multipliers = Pseudo::JacobiRefined;
		Extra.push_back({"Dalone_ref_1e-10", false, [O](const Problem& P, const VecX*) { return D(P, O); }});
		O.FloorStiffSlip = true;
		Extra.push_back({"Dalone_ref_1e-10_floor", false, [O](const Problem& P, const VecX*) { return D(P, O); }});
		for (double Floor : {1e-4, 1e-5, 1e-7, 1e-8})
			for (Pseudo Kind : {Pseudo::JacobiCutoff, Pseudo::JacobiRefined})
			{
				DOptions F = O;
				F.Multipliers = Kind;
				F.StiffSlipFloor = Floor;
				char Name[48];
				std::snprintf(Name, sizeof Name, "Dalone_%s_floor%.0e", Kind == Pseudo::JacobiCutoff ? "cut" : "ref", Floor);
				Extra.push_back({Name, false, [F](const Problem& P, const VecX*) { return D(P, F); }});
			}
		DOptions F = O;
		F.Multipliers = Pseudo::JacobiCutoff;
		Extra.push_back({"Dalone_cut_floor1e-06", false, [F](const Problem& P, const VecX*) { return D(P, F); }});
	}
	std::vector<Method> All = Methods;
	All.insert(All.end(), Extra.begin(), Extra.end());
	// Optional comma-separated filter of method names.
	std::vector<Method> Chosen;
	if (Argc > 5)
	{
		const std::string Filter = std::string(",") + Argv[5] + ",";
		for (const Method& M : All)
			if (Filter.find("," + M.Name + ",") != std::string::npos) Chosen.push_back(M);
	}
	else
	{
		Chosen = Methods;
	}

	std::FILE* Out = std::fopen(Argv[3], "w");
	std::fprintf(Out, "window,index,method,natural,natural_python_d,dq_vs_python_d,dv_vs_ref_cmps,dw_vs_ref_radps,dspin_vs_ref,"
		"circle_excess,torque_excess,friction_power,energy_identity_error,iterations,rounds,attempts,fallback_passes,"
		"fallback_us,median_us,max_us,allocations,stopped,budget_hit,engine_natural\n");
	std::map<std::string, Memory> Warm;
	std::string LastWindow;
	for (size_t S = 0; S < Rows.size(); ++S)
	{
		const Row& R = Rows[S];
		if (R.Window != LastWindow)
		{
			Warm.clear();
			LastWindow = R.Window;
		}
		const Problem P = Build(R.In);
		const double EngineNatural = NaturalResidual(P, EngineX(R.In));
		std::vector<Result> Results;
		std::vector<double> Medians, Maxes;
		std::vector<std::uint64_t> Allocs;
		for (const Method& M : Chosen)
		{
			VecX Start{};
			const VecX* StartPtr = nullptr;
			if (M.Warm && Warm[M.Name].Valid)
			{
				Start = WarmStart(P, Warm[M.Name]);
				StartPtr = &Start;
			}
			std::vector<double> Times(Repeats);
			Result Res;
			std::uint64_t Seen = 0;
			for (int Rep = 0; Rep < Repeats; ++Rep)
			{
				// Count allocations, and read the clock, around the solve alone.
				const std::uint64_t Before = Allocations;
				const auto T0 = std::chrono::steady_clock::now();
				Res = M.Solve(P, StartPtr);
				const auto T1 = std::chrono::steady_clock::now();
				Seen += Allocations - Before;
				Times[Rep] = std::chrono::duration<double, std::micro>(T1 - T0).count();
			}
			Allocs.push_back(Seen);
			std::sort(Times.begin(), Times.end());
			Medians.push_back(Times[Times.size() / 2]);
			Maxes.push_back(Times.back());
			if (M.Warm) Remember(P, Res.X, Warm[M.Name]);
			Results.push_back(Res);
		}
		// Reference: the most nearly optimal answer here, Python D's included.
		VecQ RefQ = Py[S].Q;
		double RefNatural = Py[S].Natural;
		for (const Result& Res : Results)
			if (Res.Natural < RefNatural)
			{
				RefNatural = Res.Natural;
				RefQ = VelocityAfter(P, Res.X);
			}
		const VecQ PyQ = VelocityAfter(P, Py[S].X);
		for (size_t K = 0; K < Chosen.size(); ++K)
		{
			const Result& Res = Results[K];
			const Checks C = Evaluate(P, Res.X);
			double DqPy = 0;
			for (int J = 0; J < NQ; ++J) DqPy = std::max(DqPy, std::abs(C.Q[J] - PyQ[J]));
			std::fprintf(Out, "%s,%d,%s,%.6e,%.6e,%.6e,%.6e,%.6e,%.6e,%.6e,%.6e,%.6e,%.6e,%d,%d,%d,%d,%.3f,%.3f,%.3f,%llu,%d,%d,%.6e\n",
				R.Window.c_str(), R.Index, Chosen[K].Name.c_str(), C.Natural, Py[S].Natural, DqPy, Distance3(C.Q, RefQ, 0),
				Distance3(C.Q, RefQ, 3), DistanceSpins(C.Q, RefQ), C.CircleExcess, C.TorqueExcess, C.FrictionPower,
				C.EnergyIdentityError, Res.Iterations, Res.Rounds, Res.Attempts, Res.FallbackPasses, Res.FallbackSeconds * 1e6,
				Medians[K], Maxes[K], static_cast<unsigned long long>(Allocs[K]), Res.Stopped ? 1 : 0, Res.BudgetHit ? 1 : 0,
				EngineNatural);
		}
	}
	std::fclose(Out);
	rusage Usage{};
	getrusage(RUSAGE_SELF, &Usage);
	std::printf("{\"states\": %zu, \"methods\": %zu, \"repeats\": %d, \"peak_rss_kb\": %ld}\n", Rows.size(), Chosen.size(),
		Repeats, Usage.ru_maxrss / 1024);
	return 0;
}
