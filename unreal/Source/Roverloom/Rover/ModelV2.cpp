#include "ModelV2.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

namespace RoverloomModelV2
{
	bool Load(FMeshes& Out)
	{
		FString Model;
		FParse::Value(FCommandLine::Get(), TEXT("RoverModel="), Model);
		if (Model == TEXT("greybox"))
		{
			return false;
		}
		auto Get = [](const TCHAR* Path) { return LoadObject<UStaticMesh>(nullptr, Path, nullptr, LOAD_NoWarn | LOAD_Quiet); };
		Out.Body = Get(TEXT("/Game/Rover/SM_RoverBody.SM_RoverBody"));
		Out.Wheel = Get(TEXT("/Game/Rover/SM_RoverWheel.SM_RoverWheel"));
		Out.Strut = Get(TEXT("/Game/Rover/SM_RoverStrut.SM_RoverStrut"));
		Out.Axle = Get(TEXT("/Game/Rover/SM_RoverAxle.SM_RoverAxle"));
		return Out.Body && Out.Wheel && Out.Strut && Out.Axle;
	}

	void PaintBody(UStaticMeshComponent* Body, const FLinearColor& Color)
	{
		if (!Body || !Body->GetStaticMesh())
		{
			return;
		}
		const int32 Slot = Body->GetMaterialIndex(TEXT("M_RoverBody"));
		if (Slot == INDEX_NONE)
		{
			return;
		}
		if (UMaterialInstanceDynamic* Material = Body->CreateDynamicMaterialInstance(Slot))
		{
			Material->SetVectorParameterValue(TEXT("Paint"), Color);
		}
	}

	FVector AxleScale(const UStaticMesh* Axle, double MountY)
	{
		const FBox Box = Axle->GetBoundingBox();
		const bool bPointsPlusY = Box.Max.Y > -Box.Min.Y;
		const bool bNeedsPlusY = MountY < 0.0;
		return FVector(1.0, bNeedsPlusY == bPointsPlusY ? 1.0 : -1.0, 1.0);
	}
}
