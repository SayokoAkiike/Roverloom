#include "CommandRouter.h"

namespace RoverloomCommand
{
	bool IsClose(double A, double B)
	{
		if (A == B)
		{
			return true;
		}
		return FMath::Abs(A - B) <= 1e-9 * FMath::Max(FMath::Abs(A), FMath::Abs(B));
	}

	FCommandRouter::FCommandRouter(const TArray<FString>& InSources, const FString& InActive, double InMaxSpeedMps,
		double InMaxYawRateRadps, double InWatchdogTimeoutS)
		: Sources(InSources)
		, Active(InActive)
		, MaxSpeedMps(InMaxSpeedMps)
		, MaxYawRateRadps(InMaxYawRateRadps)
		, TimeoutS(InWatchdogTimeoutS)
	{
		checkf(Sources.Contains(Active), TEXT("active source is not registered: %s"), *Active);
	}

	bool FCommandRouter::SetActive(const FString& Source)
	{
		if (!Sources.Contains(Source))
		{
			return false;
		}
		if (Source != Active)
		{
			Active = Source;
			CurrentAction = FAction();
			LastAcceptS.Reset();
		}
		return true;
	}

	FCommandRecord FCommandRouter::Submit(const FString& Source, const FAction& Action, double TimeS)
	{
		FCommandRecord Record;
		Record.TimeS = TimeS;
		Record.Source = Source;
		Record.Requested = Action;
		if (!Sources.Contains(Source))
		{
			Record.RejectedReason = TEXT("unknown_source");
			return Record;
		}
		if (Source != Active)
		{
			Record.RejectedReason = TEXT("inactive_source");
			return Record;
		}
		// Python's Action refuses non-finite values when it is built, so such a command never reaches its router.
		if (!FMath::IsFinite(Action.LinearVelocityMps) || !FMath::IsFinite(Action.YawRateRadps))
		{
			Record.RejectedReason = TEXT("non_finite_action");
			return Record;
		}
		FAction Applied;
		Applied.LinearVelocityMps = FMath::Clamp(Action.LinearVelocityMps, -MaxSpeedMps, MaxSpeedMps);
		Applied.YawRateRadps = FMath::Clamp(Action.YawRateRadps, -MaxYawRateRadps, MaxYawRateRadps);
		Record.bClamped = !(IsClose(Applied.LinearVelocityMps, Action.LinearVelocityMps) && IsClose(Applied.YawRateRadps, Action.YawRateRadps));
		Record.Applied = Applied;
		CurrentAction = Applied;
		LastAcceptS = TimeS;
		return Record;
	}

	bool FCommandRouter::WatchdogExpired(double TimeS) const
	{
		return !LastAcceptS.IsSet() || TimeS - LastAcceptS.GetValue() > TimeoutS;
	}

	FAction FCommandRouter::Current(double TimeS) const
	{
		return WatchdogExpired(TimeS) ? FAction() : CurrentAction;
	}
}
