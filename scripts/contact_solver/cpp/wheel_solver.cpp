// Contact solver research, C++ port of scripts/contact_solver/problem.py and methods.py.
// Each function follows its Python counterpart line for line unless an option says otherwise.
#include "wheel_solver.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>

namespace wheel_solver
{
	std::uint64_t Allocations = 0;

	namespace
	{
		double Dot3(const double* A, const double* B) { return A[0] * B[0] + A[1] * B[1] + A[2] * B[2]; }

		void Cross3(const double* A, const double* B, double* Out)
		{
			const double X = A[1] * B[2] - A[2] * B[1], Y = A[2] * B[0] - A[0] * B[2], Z = A[0] * B[1] - A[1] * B[0];
			Out[0] = X;
			Out[1] = Y;
			Out[2] = Z;
		}

		double DotQ(const VecQ& A, const VecQ& B)
		{
			double S = 0;
			for (int K = 0; K < NQ; ++K) S += A[K] * B[K];
			return S;
		}

		Mat3 Invert3(const Mat3& M)
		{
			const double A = M[0][0], B = M[0][1], C = M[0][2], D = M[1][0], E = M[1][1], F = M[1][2], G = M[2][0],
				H = M[2][1], I = M[2][2];
			const double Det = A * (E * I - F * H) - B * (D * I - F * G) + C * (D * H - E * G);
			Mat3 R{};
			R[0] = {(E * I - F * H) / Det, (C * H - B * I) / Det, (B * F - C * E) / Det};
			R[1] = {(F * G - D * I) / Det, (A * I - C * G) / Det, (C * D - A * F) / Det};
			R[2] = {(D * H - E * G) / Det, (B * G - A * H) / Det, (A * E - B * D) / Det};
			return R;
		}

		// Cholesky solve of an n x n symmetric matrix held in an N x N array. Returns false if not positive definite.
		template <int N>
		bool CholeskySolve(const std::array<std::array<double, N>, N>& A, int Size, const std::array<double, N>& Rhs,
			std::array<double, N>& Out)
		{
			std::array<std::array<double, N>, N> L{};
			for (int I = 0; I < Size; ++I)
			{
				for (int J = 0; J <= I; ++J)
				{
					double S = A[I][J];
					for (int K = 0; K < J; ++K) S -= L[I][K] * L[J][K];
					if (I == J)
					{
						if (S <= 0) return false;
						L[I][I] = std::sqrt(S);
					}
					else
					{
						L[I][J] = S / L[J][J];
					}
				}
			}
			std::array<double, N> Y{};
			for (int I = 0; I < Size; ++I)
			{
				double S = Rhs[I];
				for (int K = 0; K < I; ++K) S -= L[I][K] * Y[K];
				Y[I] = S / L[I][I];
			}
			for (int I = Size - 1; I >= 0; --I)
			{
				double S = Y[I];
				for (int K = I + 1; K < Size; ++K) S -= L[K][I] * Out[K];
				Out[I] = S / L[I][I];
			}
			return true;
		}

		// Factor once; if rounding breaks positive definiteness, shift the diagonal from 1e-14 of its mean, tenfold.
		struct RobustSolver
		{
			std::array<std::array<double, NQ>, NQ> H{};
			void Prepare(const std::array<std::array<double, NQ>, NQ>& In)
			{
				double Scale = 0;
				for (int I = 0; I < NQ; ++I) Scale += In[I][I];
				Scale /= NQ;
				double Shift = 0;
				std::array<double, NQ> Zero{}, Probe{};
				for (;;)
				{
					H = In;
					for (int I = 0; I < NQ; ++I) H[I][I] += Shift;
					if (CholeskySolve<NQ>(H, NQ, Zero, Probe)) return;
					Shift = Shift == 0 ? 1e-14 * Scale : Shift * 10;
				}
			}
			VecQ Solve(const VecQ& B) const
			{
				VecQ X{};
				CholeskySolve<NQ>(H, NQ, B, X);
				return X;
			}
		};

		using MatX = std::array<VecX, NX>;

		// Cyclic Jacobi eigen-decomposition of an n x n symmetric matrix (n <= 18), as the Python prototype.
		void SymmetricEigen(const MatX& In, int N, VecX& Values, MatX& Vectors)
		{
			MatX M = In;
			for (int I = 0; I < N; ++I)
				for (int J = 0; J < N; ++J) Vectors[I][J] = I == J ? 1.0 : 0.0;
			for (int Sweep = 0; Sweep < 60; ++Sweep)
			{
				double Off = 0, Diag = 0;
				for (int I = 0; I < N; ++I)
					for (int J = 0; J < N; ++J) (I == J ? Diag : Off) += M[I][J] * M[I][J];
				if (Off <= 1e-30 * Diag) break;
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
			}
			for (int I = 0; I < N; ++I) Values[I] = M[I][I];
		}

		// Minimum-norm least-squares step for a symmetric positive semidefinite S.
		VecX PseudoSolve(const MatX& S, int N, const VecX& B, Pseudo Kind, double Cutoff)
		{
			VecX X{};
			if (Kind != Pseudo::TikhonovRefined)
			{
				VecX Values{};
				MatX Vectors{};
				SymmetricEigen(S, N, Values, Vectors);
				double Top = 0;
				for (int I = 0; I < N; ++I) Top = std::max(Top, std::abs(Values[I]));
				// Apply the truncated pseudo-inverse to a right-hand side.
				auto Apply = [&](const VecX& Rhs, VecX& Out) {
					for (int K = 0; K < N; ++K)
					{
						if (Values[K] <= Cutoff * Top) continue;
						double C = 0;
						for (int I = 0; I < N; ++I) C += Vectors[I][K] * Rhs[I];
						C /= Values[K];
						for (int I = 0; I < N; ++I) Out[I] += C * Vectors[I][K];
					}
				};
				Apply(B, X);
				if (Kind == Pseudo::JacobiRefined)
					for (int Pass = 0; Pass < 2; ++Pass)
					{
						// The remainder's part in the kept eigenspace, solved again: removes rounding there.
						VecX Rest{};
						for (int I = 0; I < N; ++I)
						{
							double Sx = 0;
							for (int J = 0; J < N; ++J) Sx += S[I][J] * X[J];
							Rest[I] = B[I] - Sx;
						}
						Apply(Rest, X);
					}
				return X;
			}
			// (S + delta I) y = b, refined: each pass solves for the remainder b - S y. For a consistent system
			// this converges to the pseudo-inverse solution, without a hard cut on small eigenvalues.
			double Top = 0;
			for (int I = 0; I < N; ++I) Top = std::max(Top, S[I][I]);
			MatX R = S;
			for (int I = 0; I < N; ++I) R[I][I] += 1e-12 * Top;
			VecX Rest = B;
			for (int Pass = 0; Pass < 30; ++Pass)
			{
				VecX Step{};
				if (!CholeskySolve<NX>(R, N, Rest, Step)) break;
				double Change = 0, Size = 0;
				for (int I = 0; I < N; ++I)
				{
					X[I] += Step[I];
					Change = std::max(Change, std::abs(Step[I]));
					Size = std::max(Size, std::abs(X[I]));
				}
				for (int I = 0; I < N; ++I)
				{
					double Sx = 0;
					for (int J = 0; J < N; ++J) Sx += S[I][J] * X[J];
					Rest[I] = B[I] - Sx;
				}
				if (Change <= 1e-16 * (1 + Size)) break;
			}
			return X;
		}

		VecX Project(const Problem& P, VecX X)
		{
			for (int I = 0; I < Wheels; ++I)
			{
				const double Limit = P.FrictionLimit[I];
				const double Size = std::hypot(X[3 * I], X[3 * I + 1]);
				if (Size > Limit)
				{
					const double Scale = Size > 0 ? Limit / Size : 0.0;
					X[3 * I] *= Scale;
					X[3 * I + 1] *= Scale;
				}
				const double L = P.TorqueLimit[I];
				X[3 * I + 2] = std::min(std::max(X[3 * I + 2], -L), L);
			}
			return X;
		}

		double NaturalWith(const Problem& P, const MatX& A, const VecX& X)
		{
			VecX W{};
			for (int R = 0; R < NX; ++R)
			{
				double S = P.B[R];
				for (int C = 0; C < NX; ++C) S += A[R][C] * X[C];
				W[R] = S;
			}
			double Worst = 0;
			for (int I = 0; I < Wheels; ++I)
			{
				const double Limit = P.FrictionLimit[I];
				if (P.InContact[I] && Limit > 0)
				{
					const double Rho = 1.0 / std::max(A[3 * I][3 * I], A[3 * I + 1][3 * I + 1]);
					double Tx = X[3 * I] - Rho * W[3 * I], Ty = X[3 * I + 1] - Rho * W[3 * I + 1];
					const double Ts = std::hypot(Tx, Ty);
					if (Ts > Limit)
					{
						Tx *= Limit / Ts;
						Ty *= Limit / Ts;
					}
					Worst = std::max(Worst, std::hypot(X[3 * I] - Tx, X[3 * I + 1] - Ty) / Limit);
				}
				const double L = P.TorqueLimit[I];
				if (L > 0)
				{
					const double Rho = 1.0 / A[3 * I + 2][3 * I + 2];
					const double Trial = std::min(std::max(X[3 * I + 2] - Rho * W[3 * I + 2], -L), L);
					Worst = std::max(Worst, std::abs(X[3 * I + 2] - Trial) / L);
				}
			}
			return Worst;
		}

		// Minimize 0.5 F'BF + g'F over |F| <= limit.
		void DiskBlock(const double G[2], const double B[2][2], double Limit, double Out[2])
		{
			auto At = [&](double Lam, double R[2]) {
				const double D00 = B[0][0] + Lam, D11 = B[1][1] + Lam;
				const double Det = D00 * D11 - B[0][1] * B[1][0];
				R[0] = -(D11 * G[0] - B[0][1] * G[1]) / Det;
				R[1] = -(D00 * G[1] - B[1][0] * G[0]) / Det;
			};
			At(0.0, Out);
			if (std::hypot(Out[0], Out[1]) <= Limit) return;
			if (Limit <= 0)
			{
				Out[0] = Out[1] = 0;
				return;
			}
			double Low = 0, High = std::hypot(G[0], G[1]) / Limit, Trial[2];
			for (int K = 0; K < 100; ++K)
			{
				const double Mid = 0.5 * (Low + High);
				At(Mid, Trial);
				(std::hypot(Trial[0], Trial[1]) > Limit ? Low : High) = Mid;
			}
			At(High, Out);
			const double Size = std::hypot(Out[0], Out[1]);
			Out[0] *= Limit / Size;
			Out[1] *= Limit / Size;
		}

		void WheelBlock(const double G[3], const double B[3][3], double Limit, double TorqueLimit, double Out[3])
		{
			double B2[2][2] = {{B[0][0], B[0][1]}, {B[1][0], B[1][1]}};
			if (TorqueLimit <= 0)
			{
				DiskBlock(G, B2, Limit, Out);
				Out[2] = 0;
				return;
			}
			const double Btt = B[2][2];
			const double Rg[2] = {G[0] - B[0][2] * G[2] / Btt, G[1] - B[1][2] * G[2] / Btt};
			double Rb[2][2];
			for (int K = 0; K < 2; ++K)
				for (int M = 0; M < 2; ++M) Rb[K][M] = B[K][M] - B[K][2] * B[2][M] / Btt;
			DiskBlock(Rg, Rb, Limit, Out);
			double Tau = -(G[2] + B[2][0] * Out[0] + B[2][1] * Out[1]) / Btt;
			if (std::abs(Tau) <= TorqueLimit)
			{
				Out[2] = Tau;
				return;
			}
			Tau = std::copysign(TorqueLimit, Tau);
			const double Sg[2] = {G[0] + B[0][2] * Tau, G[1] + B[1][2] * Tau};
			DiskBlock(Sg, B2, Limit, Out);
			Out[2] = Tau;
		}

		// One nonsmooth term: a contact (2 rows) or a motor or brake (1 row).
		struct Term
		{
			int Wheel = 0, Count = 0;
			bool Contact = false;
			double Weight = 0, Scale = 1;
			const VecQ* Rows[2]{};
			double Offs[2]{};
		};

		int MakeTerms(const Problem& P, Term* Terms)
		{
			int N = 0;
			for (int I = 0; I < Wheels; ++I)
			{
				if (P.InContact[I] && P.FrictionLimit[I] > 0)
				{
					Term& T = Terms[N++];
					T = {I, 2, true, P.Dt * P.FrictionLimit[I], 1.0, {&P.Rows[3 * I], &P.Rows[3 * I + 1]},
						{P.Offsets[3 * I], P.Offsets[3 * I + 1]}};
				}
				if (P.TorqueLimit[I] > 0)
				{
					Term& T = Terms[N++];
					T = {I, 1, false, P.Dt * P.TorqueLimit[I], 1.0 / P.Radius, {&P.Rows[3 * I + 2], nullptr},
						{P.Offsets[3 * I + 2], 0}};
				}
			}
			return N;
		}

		void Z(const Term& T, const VecQ& Q, double Out[2])
		{
			for (int A = 0; A < T.Count; ++A) Out[A] = DotQ(*T.Rows[A], Q) - T.Offs[A];
		}

		double Norm(const double* V, int N) { return N == 2 ? std::hypot(V[0], V[1]) : std::abs(V[0]); }

		std::array<std::array<double, NQ>, NQ> MassMatrix(const Problem& P)
		{
			std::array<std::array<double, NQ>, NQ> M{};
			for (int K = 0; K < 3; ++K) M[K][K] = P.Mass;
			for (int K = 0; K < 3; ++K)
				for (int J = 0; J < 3; ++J) M[3 + K][3 + J] = P.Inertia[K][J];
			for (int K = 6; K < NQ; ++K) M[K][K] = P.WheelInertia;
			return M;
		}

		void AddOuter(std::array<std::array<double, NQ>, NQ>& H, const VecQ& Ra, const VecQ& Rb, double Value)
		{
			if (Value == 0) return;
			for (int C = 0; C < NQ; ++C)
			{
				if (Ra[C] == 0) continue;
				for (int E = 0; E < NQ; ++E)
					if (Rb[E] != 0) H[C][E] += Value * Ra[C] * Rb[E];
			}
		}

		VecX ForcesFrom(const Problem& P, const Term* Terms, int N, const double (*Nvec)[2])
		{
			VecX X{};
			for (int K = 0; K < N; ++K)
			{
				const Term& T = Terms[K];
				if (T.Contact)
				{
					X[3 * T.Wheel] = -T.Weight * Nvec[K][0] / P.Dt;
					X[3 * T.Wheel + 1] = -T.Weight * Nvec[K][1] / P.Dt;
				}
				else
				{
					X[3 * T.Wheel + 2] = -T.Weight * Nvec[K][0] / P.Dt;
				}
			}
			return X;
		}

		struct Predicted
		{
			VecQ Q{};
			double Eps = 0, Natural = 0;
			int Iterations = 0;
		};

		double Now() { return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count(); }

		// The slowest Newton step so far in this solve, so that a step is not begun if it might overrun.
		struct StepClock
		{
			double Slowest = 0, Last = 0;
			bool Denied = false; // A step was refused for lack of time
			bool Allows(double Deadline)
			{
				const double T = Now();
				if (Last > 0) Slowest = std::max(Slowest, T - Last);
				Last = T;
				const bool Ok = T + Slowest <= Deadline;
				Denied = Denied || !Ok;
				return Ok;
			}
		};
		thread_local StepClock StepTimer;

		Predicted SmoothedNewton(const Problem& P, const Term* Terms, int N, double EpsFinal, double EpsStart, int& Budget,
			double Deadline)
		{
			const auto Mass = MassMatrix(P);
			VecQ Q = P.QStar;
			double Eps = std::max(EpsStart, EpsFinal);
			Predicted Best;
			Best.Natural = std::numeric_limits<double>::infinity();
			int Steps = 0;
			for (;;)
			{
				double Size = 0;
				for (int K = 0; K < N; ++K) Size += Terms[K].Weight * Eps * Terms[K].Scale;
				for (int It = 0; It < 60 && Budget > 0 && StepTimer.Allows(Deadline); ++It, --Budget)
				{
					VecQ D{};
					for (int K = 0; K < NQ; ++K) D[K] = Q[K] - P.QStar[K];
					VecQ Grad = MassApply(P, D);
					auto H = Mass;
					for (int K = 0; K < N; ++K)
					{
						const Term& T = Terms[K];
						double Zv[2];
						Z(T, Q, Zv);
						const double E = Eps * T.Scale;
						const double S = std::sqrt(Zv[0] * Zv[0] + (T.Count == 2 ? Zv[1] * Zv[1] : 0) + E * E);
						for (int A = 0; A < T.Count; ++A)
							for (int C = 0; C < NQ; ++C) Grad[C] += T.Weight * Zv[A] / S * (*T.Rows[A])[C];
						for (int A = 0; A < T.Count; ++A)
							for (int Bi = 0; Bi < T.Count; ++Bi)
								AddOuter(H, *T.Rows[A], *T.Rows[Bi],
									T.Weight * ((A == Bi ? 1.0 / S : 0.0) - Zv[A] * Zv[Bi] / (S * S * S)));
					}
					VecQ NegGrad{};
					for (int K = 0; K < NQ; ++K) NegGrad[K] = -Grad[K];
					RobustSolver Rs;
					Rs.Prepare(H);
					const VecQ Step = Rs.Solve(NegGrad);
					const double Predicted = -DotQ(Grad, Step);
					++Steps;
					if (Predicted <= 1e-8 * Size) break;
					// phi(q + alpha step) - phi(q), without subtracting two large numbers.
					auto Change = [&](double Alpha) {
						const VecQ Ms = MassApply(P, Step);
						double Total = Alpha * DotQ(D, Ms) + 0.5 * Alpha * Alpha * DotQ(Step, Ms);
						VecQ Nq{};
						for (int K = 0; K < NQ; ++K) Nq[K] = Q[K] + Alpha * Step[K];
						for (int K = 0; K < N; ++K)
						{
							const Term& T = Terms[K];
							double Z0[2] = {0, 0}, Z1[2] = {0, 0};
							Z(T, Q, Z0);
							Z(T, Nq, Z1);
							const double E = Eps * T.Scale;
							const double A0 = Z0[0] * Z0[0] + Z0[1] * Z0[1], A1 = Z1[0] * Z1[0] + Z1[1] * Z1[1];
							Total += T.Weight * (A1 - A0) / (std::sqrt(A0 + E * E) + std::sqrt(A1 + E * E));
						}
						return Total;
					};
					double Alpha = 1.0;
					while (Alpha > 1e-12 && Change(Alpha) > -0.25 * Alpha * Predicted) Alpha *= 0.5;
					if (Alpha <= 1e-12) break;
					for (int K = 0; K < NQ; ++K) Q[K] += Alpha * Step[K];
				}
				double Nv[2 * Wheels][2]{};
				for (int K = 0; K < N; ++K)
				{
					const Term& T = Terms[K];
					double Zv[2] = {0, 0};
					Z(T, Q, Zv);
					const double E = Eps * T.Scale;
					const double S = std::sqrt(Zv[0] * Zv[0] + Zv[1] * Zv[1] + E * E);
					Nv[K][0] = Zv[0] / S;
					Nv[K][1] = Zv[1] / S;
				}
				const double Residual = NaturalResidual(P, ForcesFrom(P, Terms, N, Nv));
				if (Residual < Best.Natural)
				{
					Best.Q = Q;
					Best.Eps = Eps;
					Best.Natural = Residual;
				}
				if (Eps <= EpsFinal || Budget <= 0 || Now() > Deadline) break;
				Eps = std::max(Eps * 0.1, EpsFinal);
			}
			Best.Iterations = Steps;
			return Best;
		}

		struct Partition
		{
			VecQ Q{};
			double N[2 * Wheels][2]{}; // Each term's multiplier: n where held, z/|z| where sliding
			VecX X{};
			bool Converged = false;
			int Steps = 0;
		};

		Partition SolvePartition(const Problem& P, const Term* Terms, int N, const bool* Fixed, const VecQ& Q0,
			const double (*Priors)[2], const DOptions& O, int& Budget, double Deadline)
		{
			const auto Mass = MassMatrix(P);
			Partition Out;
			VecQ Q = Q0;
			int Held[2 * Wheels], Rows = 0, Base[2 * Wheels];
			int NHeld = 0;
			for (int K = 0; K < N; ++K)
				if (Fixed[K])
				{
					Held[NHeld++] = K;
					Base[K] = Rows;
					Rows += Terms[K].Count;
				}
			VecX Lam{};
			for (int H = 0; H < NHeld; ++H)
				for (int A = 0; A < Terms[Held[H]].Count; ++A) Lam[Base[Held[H]] + A] = Priors[Held[H]][A];
			// The residual of the conditions, for the optional line search.
			auto Merit = [&](const VecQ& Qv, const VecX& Lv) {
				VecQ D{};
				for (int K = 0; K < NQ; ++K) D[K] = Qv[K] - P.QStar[K];
				VecQ R1 = MassApply(P, D);
				double R2 = 0;
				for (int K = 0; K < N; ++K)
				{
					const Term& T = Terms[K];
					double Zv[2] = {0, 0};
					Z(T, Qv, Zv);
					if (Fixed[K])
					{
						for (int A = 0; A < T.Count; ++A)
						{
							for (int C = 0; C < NQ; ++C) R1[C] += T.Weight * (*T.Rows[A])[C] * Lv[Base[K] + A];
							R2 += (T.Weight * Zv[A]) * (T.Weight * Zv[A]);
						}
						continue;
					}
					const double Nz = Norm(Zv, T.Count);
					if (Nz <= 1e-10 * T.Scale) continue;
					for (int A = 0; A < T.Count; ++A)
						for (int C = 0; C < NQ; ++C) R1[C] += T.Weight * Zv[A] / Nz * (*T.Rows[A])[C];
				}
				return DotQ(R1, R1) + R2;
			};
			for (int It = 0; It < O.MaxNewtonPerPartition && Budget > 0 && StepTimer.Allows(Deadline); ++It, --Budget)
			{
				++Out.Steps;
				VecQ D{};
				for (int K = 0; K < NQ; ++K) D[K] = Q[K] - P.QStar[K];
				VecQ R1 = MassApply(P, D);
				auto H = Mass;
				for (int K = 0; K < N; ++K)
				{
					if (Fixed[K]) continue;
					const Term& T = Terms[K];
					double Zv[2] = {0, 0};
					Z(T, Q, Zv);
					const double Nz = Norm(Zv, T.Count);
					if (Nz <= 1e-10 * T.Scale) continue; // A slip this small is a stick; its 1/|z| would swamp the rest
					for (int A = 0; A < T.Count; ++A)
						for (int C = 0; C < NQ; ++C) R1[C] += T.Weight * Zv[A] / Nz * (*T.Rows[A])[C];
					// Optionally floor |z| in the Hessian only: a slower but stable Newton near zero slip.
					const double Nh = O.FloorStiffSlip ? std::max(Nz, O.StiffSlipFloor * T.Scale) : Nz;
					for (int A = 0; A < T.Count; ++A)
						for (int Bi = 0; Bi < T.Count; ++Bi)
							AddOuter(H, *T.Rows[A], *T.Rows[Bi],
								T.Weight * ((A == Bi ? 1.0 / Nh : 0.0) - Zv[A] * Zv[Bi] / (Nh * Nz * Nz)));
				}
				std::array<VecQ, NX> Srow{};
				VecX R2{};
				for (int Hh = 0; Hh < NHeld; ++Hh)
				{
					const Term& T = Terms[Held[Hh]];
					double Zv[2] = {0, 0};
					Z(T, Q, Zv);
					for (int A = 0; A < T.Count; ++A)
					{
						const int R = Base[Held[Hh]] + A;
						for (int C = 0; C < NQ; ++C)
						{
							Srow[R][C] = T.Weight * (*T.Rows[A])[C];
							R1[C] += Srow[R][C] * Lam[R];
						}
						R2[R] = T.Weight * Zv[A];
					}
				}
				RobustSolver Rs;
				Rs.Prepare(H);
				const VecQ HinvR1 = Rs.Solve(R1);
				VecQ Dq{};
				VecX Dl{};
				if (Rows)
				{
					std::array<VecQ, NX> HinvSt{};
					for (int J = 0; J < Rows; ++J) HinvSt[J] = Rs.Solve(Srow[J]);
					MatX Schur{};
					VecX Rhs{};
					for (int I = 0; I < Rows; ++I)
					{
						for (int J = 0; J < Rows; ++J) Schur[I][J] = DotQ(Srow[I], HinvSt[J]);
						Rhs[I] = R2[I] - DotQ(Srow[I], HinvR1);
					}
					Dl = PseudoSolve(Schur, Rows, Rhs, O.Multipliers, O.Cutoff);
					for (int C = 0; C < NQ; ++C)
					{
						double S = HinvR1[C];
						for (int J = 0; J < Rows; ++J) S += HinvSt[J][C] * Dl[J];
						Dq[C] = -S;
					}
				}
				else
				{
					for (int C = 0; C < NQ; ++C) Dq[C] = -HinvR1[C];
				}
				double Alpha = 1.0;
				if (O.FloorStiffSlip)
				{
					// With the floored Hessian, a full step can overshoot: halve while the residual grows.
					const double Before = Merit(Q, Lam);
					for (int Tries = 0; Tries < 30; ++Tries)
					{
						VecQ Qt{};
						VecX Lt = Lam;
						for (int C = 0; C < NQ; ++C) Qt[C] = Q[C] + Alpha * Dq[C];
						for (int J = 0; J < Rows; ++J) Lt[J] += Alpha * Dl[J];
						if (Merit(Qt, Lt) <= Before) break;
						Alpha *= 0.5;
					}
				}
				for (int C = 0; C < NQ; ++C) Q[C] += Alpha * Dq[C];
				for (int J = 0; J < Rows; ++J) Lam[J] += Alpha * Dl[J];
				if (O.History && It < 64)
				{
					O.History->Steps = It + 1;
					O.History->StepNorm[It] = std::sqrt(DotQ(Dq, Dq));
					O.History->Alpha[It] = Alpha;
					O.History->Merit[It] = Merit(Q, Lam);
				}
				const double Moved = std::sqrt(DotQ(Dq, Dq)) * (O.ConvergeOnFullStep ? 1.0 : Alpha);
				if (Moved < 1e-13 * (1.0 + std::sqrt(DotQ(Q, Q))))
				{
					Out.Converged = true;
					if (O.History) O.History->Converged = true;
					break;
				}
			}
			Out.Q = Q;
			for (int K = 0; K < N; ++K)
			{
				const Term& T = Terms[K];
				if (Fixed[K])
				{
					for (int A = 0; A < T.Count; ++A) Out.N[K][A] = Lam[Base[K] + A];
					continue;
				}
				double Zv[2] = {0, 0};
				Z(T, Q, Zv);
				const double Nz = Norm(Zv, T.Count);
				for (int A = 0; A < T.Count; ++A) Out.N[K][A] = Nz > 0 ? Zv[A] / Nz : 0.0;
			}
			Out.X = ForcesFrom(P, Terms, N, Out.N);
			return Out;
		}
	}

	Problem Build(const Input& In)
	{
		Problem P;
		P.Dt = In.Dt;
		P.Radius = In.Radius;
		P.WheelInertia = In.WheelInertia;
		P.Mass = 1.0 / In.InvMass;
		P.InvInertia = In.InvInertia;
		P.Inertia = Invert3(In.InvInertia);
		double Force[3] = {In.Ext[0], In.Ext[1], In.Ext[2]}, Torque[3] = {0, 0, 0};
		for (int I = 0; I < Wheels; ++I)
		{
			const auto& W = In.Wheel[I];
			const double Fz = W.Hit ? std::max(0.0, In.Spring * W.Comp + In.Damper * W.CompRate) : 0.0;
			P.FrictionLimit[I] = In.Friction * Fz;
			P.InContact[I] = W.Hit;
			if (W.Hit)
			{
				double Load[3] = {Fz * W.Normal[0], Fz * W.Normal[1], Fz * W.Normal[2]}, R[3], T[3];
				for (int K = 0; K < 3; ++K)
				{
					Force[K] += Load[K];
					R[K] = W.Point[K] - In.Com[K];
				}
				Cross3(R, Load, T);
				for (int K = 0; K < 3; ++K) Torque[K] += T[K];
			}
			P.TorqueLimit[I] = W.Mode == Coast ? 0.0 : (W.Mode == Brake ? In.Brake : In.Motor);
		}
		for (int K = 0; K < 3; ++K)
		{
			P.QStar[K] = In.V[K] + In.Dt * (In.Acc[K] + Force[K] * In.InvMass);
			P.QStar[3 + K] = In.W[K] + In.Dt * Dot3(In.InvInertia[K].data(), Torque);
		}
		for (int I = 0; I < Wheels; ++I) P.QStar[6 + I] = In.Wheel[I].Spin;
		for (int I = 0; I < Wheels; ++I)
		{
			const auto& W = In.Wheel[I];
			double R[3];
			for (int K = 0; K < 3; ++K)
			{
				R[K] = W.Point[K] - In.Com[K];
				P.Forward[I][K] = W.Forward[K];
				P.Lateral[I][K] = W.Lateral[K];
			}
			Cross3(R, W.Forward, P.ArmF[I]);
			Cross3(R, W.Lateral, P.ArmL[I]);
			VecQ Rf{}, Rl{}, Rm{};
			if (W.Hit)
			{
				for (int K = 0; K < 3; ++K)
				{
					Rf[K] = W.Forward[K];
					Rf[3 + K] = P.ArmF[I][K];
					Rl[K] = W.Lateral[K];
					Rl[3 + K] = P.ArmL[I][K];
				}
				Rf[6 + I] = -In.Radius;
			}
			if (W.Mode != Coast) Rm[6 + I] = 1.0;
			P.Rows[3 * I] = Rf;
			P.Rows[3 * I + 1] = Rl;
			P.Rows[3 * I + 2] = Rm;
			P.Offsets[3 * I + 2] = W.Mode == Brake ? 0.0 : (W.Mode == Coast ? 0.0 : W.Target);
		}
		std::array<VecQ, NX> Columns{};
		for (int R = 0; R < NX; ++R) Columns[R] = InvMassApply(P, P.Rows[R]);
		for (int R = 0; R < NX; ++R)
		{
			for (int C = 0; C < NX; ++C) P.A[R][C] = P.Dt * DotQ(P.Rows[R], Columns[C]);
			P.B[R] = DotQ(P.Rows[R], P.QStar) - P.Offsets[R];
		}
		return P;
	}

	VecX EngineX(const Input& In)
	{
		VecX X{};
		for (int I = 0; I < Wheels; ++I)
		{
			const auto& W = In.Wheel[I];
			X[3 * I] = W.Hit ? W.EngineLong : 0.0;
			X[3 * I + 1] = W.Hit ? W.EngineLat : 0.0;
			X[3 * I + 2] = W.Mode == Brake ? W.EngineBrake : (W.Mode == Drive ? W.EngineMotor : 0.0);
		}
		return X;
	}

	VecQ InvMassApply(const Problem& P, const VecQ& V)
	{
		VecQ Out{};
		for (int K = 0; K < 3; ++K)
		{
			Out[K] = V[K] / P.Mass;
			Out[3 + K] = P.InvInertia[K][0] * V[3] + P.InvInertia[K][1] * V[4] + P.InvInertia[K][2] * V[5];
		}
		for (int K = 6; K < NQ; ++K) Out[K] = V[K] / P.WheelInertia;
		return Out;
	}

	VecQ MassApply(const Problem& P, const VecQ& V)
	{
		VecQ Out{};
		for (int K = 0; K < 3; ++K)
		{
			Out[K] = V[K] * P.Mass;
			Out[3 + K] = P.Inertia[K][0] * V[3] + P.Inertia[K][1] * V[4] + P.Inertia[K][2] * V[5];
		}
		for (int K = 6; K < NQ; ++K) Out[K] = V[K] * P.WheelInertia;
		return Out;
	}

	VecQ VelocityAfter(const Problem& P, const VecX& X)
	{
		VecQ Impulse{};
		for (int R = 0; R < NX; ++R)
			if (X[R] != 0)
				for (int K = 0; K < NQ; ++K) Impulse[K] += P.Rows[R][K] * X[R] * P.Dt;
		const VecQ Change = InvMassApply(P, Impulse);
		VecQ Q{};
		for (int K = 0; K < NQ; ++K) Q[K] = P.QStar[K] + Change[K];
		return Q;
	}

	double NaturalResidual(const Problem& P, const VecX& X) { return NaturalWith(P, P.A, X); }

	Checks Evaluate(const Problem& P, const VecX& X)
	{
		Checks C;
		C.Q = VelocityAfter(P, X);
		C.Natural = NaturalResidual(P, X);
		VecX W{};
		for (int R = 0; R < NX; ++R) W[R] = DotQ(P.Rows[R], C.Q) - P.Offsets[R];
		for (int I = 0; I < Wheels; ++I)
		{
			const double Fx = X[3 * I], Fy = X[3 * I + 1], Tau = X[3 * I + 2];
			const double Limit = P.FrictionLimit[I], L = P.TorqueLimit[I];
			if (L > 0)
			{
				C.TorqueExcess = std::max(C.TorqueExcess, (std::abs(Tau) - L) / L);
				C.MotorPower += Tau * C.Q[6 + I];
			}
			if (!P.InContact[I] || Limit <= 0) continue;
			const double Ux = W[3 * I], Uy = W[3 * I + 1];
			const double Size = std::hypot(Fx, Fy);
			C.CircleExcess = std::max(C.CircleExcess, (Size - Limit) / Limit);
			if (Size < Limit * (1 - 1e-9))
				C.StickSlip = std::max(C.StickSlip, std::hypot(Ux, Uy));
			else if (std::hypot(Ux, Uy) > 1e-9)
				C.SlideAngleDeg = std::max(C.SlideAngleDeg,
					std::atan2(std::abs(Fx * Uy - Fy * Ux), -(Fx * Ux + Fy * Uy)) * 180.0 / M_PI);
			C.FrictionPower += Fx * Ux + Fy * Uy;
			for (int K = 0; K < 3; ++K)
			{
				C.NetForce[K] += Fx * P.Forward[I][K] + Fy * P.Lateral[I][K];
				C.NetTorque[K] += Fx * P.ArmF[I][K] + Fy * P.ArmL[I][K];
			}
		}
		const double Kinetic = 0.5 * DotQ(C.Q, MassApply(P, C.Q)) - 0.5 * DotQ(P.QStar, MassApply(P, P.QStar));
		VecQ Change{};
		for (int K = 0; K < NQ; ++K) Change[K] = C.Q[K] - P.QStar[K];
		C.Dissipation = 0.5 * DotQ(Change, MassApply(P, Change));
		C.EnergyIdentityError = Kinetic - (P.Dt * (C.FrictionPower + C.MotorPower) - C.Dissipation);
		return C;
	}

	Result Pgs(const Problem& P, const PgsOptions& O)
	{
		MatX A = P.A;
		const double SpinTerm = P.Dt * P.Radius * P.Radius / P.WheelInertia;
		if (O.Gamma != 0)
			for (int I = 0; I < NX; ++I) A[I][I] += O.Gamma * A[I][I];
		VecX X = O.Start ? Project(P, *O.Start) : VecX{};
		for (int I = 0; I < Wheels; ++I)
			if (!P.InContact[I]) X[3 * I] = X[3 * I + 1] = 0;
		VecX W{};
		for (int R = 0; R < NX; ++R)
		{
			double S = P.B[R];
			for (int C = 0; C < NX; ++C) S += A[R][C] * X[C];
			W[R] = S;
		}
		int Active[Wheels], NActive = 0;
		for (int I = 0; I < Wheels; ++I)
			if (P.InContact[I] || P.TorqueLimit[I] > 0) Active[NActive++] = I;
		Result Out;
		double Change = 0;
		int Used = 0;
		double SlowestPass = 0;
		bool TimedOut = false;
		double PassStart = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
		if (O.Deadline > 0 && PassStart > O.Deadline) Used = 0;
		for (int Step = 0; Step < O.Passes && !(O.Deadline > 0 && PassStart > O.Deadline); ++Step)
		{
			Change = 0;
			const bool Back = O.PassOrder == Order::Alternate && Step % 2 == 1;
			for (int Slot = 0; Slot < NActive; ++Slot)
			{
				const int I = Active[Back ? NActive - 1 - Slot : Slot];
				double Old[3] = {X[3 * I], X[3 * I + 1], X[3 * I + 2]}, Block[3][3], G[3], New[3];
				for (int K = 0; K < 3; ++K)
					for (int M = 0; M < 3; ++M) Block[K][M] = A[3 * I + K][3 * I + M];
				for (int K = 0; K < 3; ++K) G[K] = W[3 * I + K] - (Block[K][0] * Old[0] + Block[K][1] * Old[1] + Block[K][2] * Old[2]);
				const double Limit = P.InContact[I] ? P.FrictionLimit[I] : 0.0;
				if (Limit <= 0)
				{
					const double Tl = P.TorqueLimit[I];
					New[0] = New[1] = 0;
					New[2] = Tl > 0 ? std::min(std::max(-G[2] / Block[2][2], -Tl), Tl) : 0.0;
				}
				else
				{
					WheelBlock(G, Block, Limit, P.TorqueLimit[I], New);
				}
				for (int K = 0; K < 3; ++K)
				{
					const double Delta = New[K] - Old[K];
					if (Delta != 0)
						for (int R = 0; R < NX; ++R) W[R] += A[R][3 * I + K] * Delta;
					X[3 * I + K] = New[K];
				}
				const double BodyLong = P.A[3 * I][3 * I] - (P.InContact[I] ? SpinTerm : 0.0);
				Change = std::max({Change, std::abs(New[0] - Old[0]) * BodyLong, std::abs(New[1] - Old[1]) * P.A[3 * I + 1][3 * I + 1]});
			}
			Used = Step + 1;
			if (O.Deadline > 0)
			{
				// Stop if another pass as slow as the slowest so far would end past the deadline.
				const double Now = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
				SlowestPass = std::max(SlowestPass, Now - PassStart);
				PassStart = Now;
				if (Now + SlowestPass > O.Deadline)
				{
					TimedOut = true;
					break;
				}
			}
			if (O.StopNatural > 0)
			{
				if (Used % 5 == 0 && NaturalResidual(P, X) <= O.StopNatural) break;
			}
			else if (Change < O.Tolerance)
			{
				break;
			}
		}
		Out.X = X;
		Out.Q = VelocityAfter(P, X);
		Out.Iterations = Used;
		Out.LastChange = Change;
		Out.Natural = NaturalResidual(P, X);
		Out.Stopped = O.StopNatural > 0 ? Out.Natural <= O.StopNatural : Change < O.Tolerance;
		Out.BudgetHit = O.Deadline > 0 ? TimedOut : !Out.Stopped;
		return Out;
	}

	Result D(const Problem& P, const DOptions& O)
	{
		using Clock = std::chrono::steady_clock;
		const auto Begin = Clock::now();
		auto Elapsed = [&] { return std::chrono::duration<double>(Clock::now() - Begin).count(); };
		const double Deadline = O.MaxSeconds < 1e29 ? Now() + O.MaxSeconds - O.FinalReserve : 1e300;
		StepTimer = StepClock{};
		Term Terms[2 * Wheels];
		const int N = MakeTerms(P, Terms);
		int Budget = O.MaxNewtonTotal;
		const Predicted Pred = SmoothedNewton(P, Terms, N, O.PredictorEps, 10.0, Budget, Deadline);
		double Ratio[2 * Wheels], Priors[2 * Wheels][2]{};
		for (int K = 0; K < N; ++K)
		{
			double Zv[2] = {0, 0};
			Z(Terms[K], Pred.Q, Zv);
			const double E = Pred.Eps * Terms[K].Scale;
			const double Nz = Norm(Zv, Terms[K].Count);
			Ratio[K] = Nz / E;
			const double S = std::sqrt(Nz * Nz + E * E);
			Priors[K][0] = Zv[0] / S;
			Priors[K][1] = Zv[1] / S;
		}
		int Newton = Pred.Iterations, LastRounds = 0;
		auto Settle = [&](bool* Fixed) {
			Partition R;
			for (int Round = 1; Round <= O.MaxRounds; ++Round)
			{
				LastRounds = Round;
				R = SolvePartition(P, Terms, N, Fixed, Pred.Q, Priors, O, Budget, Deadline);
				Newton += R.Steps;
				bool Changed = false;
				for (int K = 0; K < N; ++K)
				{
					if (Fixed[K])
					{
						if (Norm(R.N[K], Terms[K].Count) > 1 + 1e-9)
						{
							Fixed[K] = false;
							Changed = true;
						}
					}
					else
					{
						double Zv[2] = {0, 0};
						Z(Terms[K], R.Q, Zv);
						if (Norm(Zv, Terms[K].Count) <= 1e-10 * Terms[K].Scale)
						{
							Fixed[K] = true;
							Changed = true;
						}
					}
				}
				if (!Changed || Budget <= 0 || Elapsed() > O.MaxSeconds) break;
			}
			return R;
		};
		bool Fixed[2 * Wheels];
		for (int K = 0; K < N; ++K) Fixed[K] = Ratio[K] <= 30;
		Partition Best = Settle(Fixed);
		double BestNatural = NaturalResidual(P, Best.X);
		const int Rounds = LastRounds;
		int Attempts = 1;
		if (BestNatural > O.Target)
			for (int K = 0; K < N && Budget > 0 && Elapsed() <= O.MaxSeconds; ++K)
			{
				if (Ratio[K] < 1 || Ratio[K] > 1e4) continue;
				bool Trial[2 * Wheels];
				for (int J = 0; J < N; ++J) Trial[J] = Ratio[J] <= 30;
				Trial[K] = !Trial[K];
				Partition R = Settle(Trial);
				const double Nat = NaturalResidual(P, R.X);
				++Attempts;
				if (Nat < BestNatural)
				{
					Best = R;
					BestNatural = Nat;
				}
				if (BestNatural <= O.Target) break;
			}
		Result Out;
		Out.X = Best.X;
		Out.Q = Best.Q;
		Out.Natural = BestNatural;
		bool FallbackTimedOut = false;
		if (BestNatural > O.Target && O.Fallback)
		{
			const auto FallBegin = Clock::now();
			PgsOptions Po;
			Po.Passes = O.FallbackPasses;
			Po.StopNatural = O.Target;
			Po.PassOrder = Order::Alternate;
			Po.Start = &Best.X;
			Po.Deadline = Deadline < 1e299 ? Deadline : 0;
			const Result Fb = Pgs(P, Po);
			FallbackTimedOut = Po.Deadline > 0 && Fb.BudgetHit;
			Out.FallbackPasses = Fb.Iterations;
			Out.FallbackSeconds = std::chrono::duration<double>(Clock::now() - FallBegin).count();
			if (Fb.Natural < Out.Natural)
			{
				Out.X = Fb.X;
				Out.Q = Fb.Q;
				Out.Natural = Fb.Natural;
			}
		}
		Out.Iterations = Newton;
		Out.Rounds = Rounds;
		Out.Attempts = Attempts;
		Out.Stopped = Out.Natural <= O.Target;
		Out.BudgetHit = Budget <= 0 || StepTimer.Denied || FallbackTimedOut || Elapsed() > O.MaxSeconds;
		return Out;
	}

	VecX MakeSafe(const Problem& P, const VecX& X, const VecX* Previous, double RejectAbove, Safety& Report)
	{
		Report = Safety{};
		auto Check = [&](const VecX& Y, bool Record) {
			bool Finite = true, Within = true, Plausible = true;
			for (double V : Y) Finite = Finite && std::isfinite(V);
			if (!Finite)
			{
				if (Record) Report.NonFinite = true;
				return false;
			}
			for (int I = 0; I < Wheels; ++I)
			{
				const double F = std::hypot(Y[3 * I], Y[3 * I + 1]);
				if ((P.FrictionLimit[I] > 0 || F > 0) && F > P.FrictionLimit[I] * (1 + 1e-9) + 1e-300) Within = false;
				if (std::abs(Y[3 * I + 2]) > P.TorqueLimit[I] * (1 + 1e-9) + 1e-300) Within = false;
			}
			const VecQ Q = VelocityAfter(P, Y);
			for (int K = 0; K < NQ; ++K)
			{
				if (!std::isfinite(Q[K])) Finite = false;
				if (std::abs(Q[K]) > (K < 6 ? 1e5 : 1e3)) Plausible = false;
			}
			const double Nat = Finite ? NaturalResidual(P, Y) : 1e300;
			if (Record)
			{
				Report.NonFinite = !Finite;
				Report.OutsideLimits = !Within;
				Report.Implausible = !Plausible;
				Report.Unconverged = Nat > RejectAbove;
				Report.Natural = Nat;
			}
			return Finite && Within && Plausible && Nat <= RejectAbove;
		};
		if (Check(X, true)) return X;
		VecX Repaired = X;
		for (double& V : Repaired)
			if (!std::isfinite(V)) V = 0;
		Repaired = Project(P, Repaired);
		for (int I = 0; I < Wheels; ++I)
			if (!P.InContact[I]) Repaired[3 * I] = Repaired[3 * I + 1] = 0;
		if (Check(Repaired, false)) return Repaired;
		if (Previous)
		{
			VecX Prior = Project(P, *Previous);
			for (int I = 0; I < Wheels; ++I)
				if (!P.InContact[I]) Prior[3 * I] = Prior[3 * I + 1] = 0;
			bool Finite = true;
			for (double V : Prior) Finite = Finite && std::isfinite(V);
			if (Finite)
			{
				Report.UsedPrevious = true;
				return Prior;
			}
		}
		Report.Zeroed = true;
		return VecX{};
	}
}
