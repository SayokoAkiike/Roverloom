#include "RaceCourse.h"

#include "Dom/JsonObject.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

#include "../Roverloom.h"

namespace
{
	bool Point(const TSharedPtr<FJsonValue>& Value, FVector2D& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
		if (!Value.IsValid() || !Value->TryGetArray(P) || P->Num() < 2)
		{
			return false;
		}
		Out = FVector2D((*P)[0]->AsNumber(), (*P)[1]->AsNumber());
		return FMath::IsFinite(Out.X) && FMath::IsFinite(Out.Y);
	}
}

namespace RoverloomRace
{
	bool LoadCourse(FRaceCourse& Out)
	{
		FString Path;
		if (!FParse::Value(FCommandLine::Get(), TEXT("RoverCourseFile="), Path))
		{
			return false;
		}
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *Path) || Text.Len() > 1024 * 1024)
		{
			UE_LOG(LogRoverloom, Error, TEXT("Race course: cannot read %s"), *Path);
			return false;
		}
		TSharedPtr<FJsonObject> Root;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
		{
			UE_LOG(LogRoverloom, Error, TEXT("Race course: %s is not JSON"), *Path);
			return false;
		}
		Root->TryGetStringField(TEXT("name"), Out.Name);
		Root->TryGetNumberField(TEXT("gate_radius_m"), Out.GateRadiusM);
		Root->TryGetNumberField(TEXT("laps"), Out.Laps);
		const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
		if (Root->TryGetArrayField(TEXT("checkpoints"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				FVector2D P;
				if (Point(V, P)) Out.Checkpoints.Add(P);
			}
		}
		if (Root->TryGetArrayField(TEXT("pads"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				FVector2D P;
				if (Point(V, P)) Out.Pads.Add(P);
			}
		}
		if (Root->TryGetArrayField(TEXT("sand"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				const TArray<TSharedPtr<FJsonValue>>* R = nullptr;
				if (V->TryGetArray(R) && R->Num() == 4)
				{
					Out.Sand.Add(FBox2D(FVector2D((*R)[0]->AsNumber(), (*R)[1]->AsNumber()), FVector2D((*R)[2]->AsNumber(), (*R)[3]->AsNumber())));
				}
			}
		}
		if (Root->TryGetArrayField(TEXT("line"), List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				FVector2D P;
				if (Point(V, P)) Out.Line.Add(P);
			}
		}
		Root->TryGetStringField(TEXT("ground"), Out.Ground);
		Root->TryGetStringField(TEXT("style"), Out.Style);
		if (Out.Checkpoints.Num() > 0)
		{
			Out.Start = Out.Checkpoints.Last();
		}
		FVector2D Start;
		if (Point(Root->TryGetField(TEXT("start")), Start))
		{
			Out.Start = Start;
		}
		Out.bLoop = Out.Checkpoints.Num() > 0 && FVector2D::Distance(Out.Start, Out.Checkpoints.Last()) < 0.5;
		if (Out.Line.Num() < 2)
		{
			Out.Line.Reset();
			Out.Line.Add(Out.Start);
			Out.Line.Append(Out.Checkpoints);
		}
		const TSharedPtr<FJsonValue> Supply = Root->TryGetField(TEXT("supply"));
		Out.bHasSupply = Point(Supply, Out.Supply);
		UE_LOG(LogRoverloom, Display, TEXT("Race course '%s': %d checkpoints, %d path points, %d sand, %d pads, style %s, ground %s"), *Out.Name,
			Out.Checkpoints.Num(), Out.Line.Num(), Out.Sand.Num(), Out.Pads.Num(), *Out.Style, *Out.Ground);
		return Out.IsValid();
	}

	double DistanceToLineM(const FRaceCourse& Course, const FVector2D& P)
	{
		double Best = TNumericLimits<double>::Max();
		for (int32 I = 0; I + 1 < Course.Line.Num(); ++I)
		{
			const FVector2D A = Course.Line[I];
			const FVector2D AB = Course.Line[I + 1] - A;
			const double T = FMath::Clamp(FVector2D::DotProduct(P - A, AB) / FMath::Max(AB.SizeSquared(), 1e-6), 0.0, 1.0);
			Best = FMath::Min(Best, FVector2D::Distance(P, A + AB * T));
		}
		return Best;
	}

	const FRaceCourse& Course()
	{
		static FRaceCourse Loaded;
		static bool bTried = false;
		if (!bTried)
		{
			bTried = true;
			LoadCourse(Loaded);
		}
		return Loaded;
	}
}
