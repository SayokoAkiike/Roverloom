#pragma once

#include "CoreMinimal.h"

// One command path for every driver, as python/src/roverloom/command.py. Contract units: m/s, and rad/s with positive
// turning left. The router knows nothing about Unreal; the pawn converts its output through Bridge/Frames.h.
namespace RoverloomCommand
{
	inline constexpr double WatchdogTimeoutS = 2.0;

	// Body-frame drive command. Positive yaw rate turns left.
	struct FAction
	{
		double LinearVelocityMps = 0.0;
		double YawRateRadps = 0.0;

		bool IsStop() const { return LinearVelocityMps == 0.0 && YawRateRadps == 0.0; }
	};

	struct FCommandRecord
	{
		double TimeS = 0.0;
		FString Source;
		FAction Requested;
		TOptional<FAction> Applied;
		bool bClamped = false;
		FString RejectedReason; // Empty when accepted
	};

	// Selects one active source, clamps commands, and stops a rover that loses contact.
	class FCommandRouter
	{
	public:
		FCommandRouter(const TArray<FString>& InSources, const FString& InActive, double InMaxSpeedMps, double InMaxYawRateRadps,
			double InWatchdogTimeoutS = WatchdogTimeoutS);

		// False for an unknown source, where Python raises. Handover starts from a stop.
		bool SetActive(const FString& Source);
		FCommandRecord Submit(const FString& Source, const FAction& Action, double TimeS);
		bool HasCommanded() const { return LastAcceptS.IsSet(); }
		bool WatchdogExpired(double TimeS) const;
		FAction Current(double TimeS) const;
		const FString& GetActive() const { return Active; }

	private:
		TArray<FString> Sources;
		FString Active;
		double MaxSpeedMps = 0.0;
		double MaxYawRateRadps = 0.0;
		double TimeoutS = WatchdogTimeoutS;
		FAction CurrentAction;
		TOptional<double> LastAcceptS;
	};

	// Python's math.isclose with its defaults: relative tolerance 1e-9, no absolute tolerance.
	bool IsClose(double A, double B);
}
