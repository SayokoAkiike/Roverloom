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
		const TSharedPtr<FJsonValue> Supply = Root->TryGetField(TEXT("supply"));
		Out.bHasSupply = Point(Supply, Out.Supply);
		UE_LOG(LogRoverloom, Display, TEXT("Race course '%s': %d checkpoints, %d sand, %d pads"), *Out.Name, Out.Checkpoints.Num(), Out.Sand.Num(), Out.Pads.Num());
		return Out.IsValid();
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
