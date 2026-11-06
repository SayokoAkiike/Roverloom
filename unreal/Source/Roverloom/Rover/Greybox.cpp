#include "Greybox.h"

#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

#include "../Roverloom.h"

namespace RoverloomGreybox
{
	void Paint(UStaticMeshComponent* Mesh, const FLinearColor& Color, float Roughness)
	{
		static const TCHAR* Path = TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial");
		UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, Path);
		if (!Mesh || !Base)
		{
			UE_LOG(LogRoverloom, Warning, TEXT("Greybox paint skipped: %s"), Base ? TEXT("no mesh") : Path);
			return;
		}
		if (UMaterialInstanceDynamic* Material = Mesh->CreateDynamicMaterialInstance(0, Base))
		{
			Material->SetVectorParameterValue(TEXT("Color"), Color);
			Material->SetScalarParameterValue(TEXT("Roughness"), Roughness);
		}
	}
}
