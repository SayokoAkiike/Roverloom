#include "GaleLandscape.h"

#include "Engine/World.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "../Roverloom.h"

#if WITH_EDITOR
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeProxy.h"
#endif

ALandscape* URoverloomLandscapeLibrary::ImportR16Landscape(UWorld* World, const FString& R16Path, int32 Samples,
	float XYScalePercent, float ZScalePercent, float OriginEastM, float OriginNorthM, float OriginGroundZCm, UMaterialInterface* Material)
{
#if WITH_EDITOR
	if (!World)
	{
		return nullptr;
	}
	TArray<uint8> Raw;
	if (!FFileHelper::LoadFileToArray(Raw, *R16Path) || Raw.Num() != Samples * Samples * 2)
	{
		UE_LOG(LogRoverloom, Error, TEXT("Landscape import: %s is not %d x %d uint16 samples (%d bytes read)"), *R16Path, Samples, Samples, Raw.Num());
		return nullptr;
	}
	TArray<uint16> Heights;
	Heights.SetNumUninitialized(Samples * Samples);
	for (int32 Index = 0; Index < Heights.Num(); ++Index)
	{
		Heights[Index] = static_cast<uint16>(Raw[2 * Index] | (Raw[2 * Index + 1] << 8)); // Little endian
	}

	// One sample is 100 cm at 100% XY scale. Unreal's height unit is 1/128 of ZScale cm, and 32768 is the actor's own Z.
	const float XYScale = XYScalePercent;
	const float ZScale = ZScalePercent;
	const int32 Quads = Samples - 1;
	// The origin point in sample coordinates. Row 0 is north, and Unreal +Y is south, so rows add to Y and north is minus.
	const double OriginCol = 0.5 * Quads + OriginEastM * 100.0 / XYScale;
	const double OriginRow = 0.5 * Quads - OriginNorthM * 100.0 / XYScale;
	const int32 C0 = FMath::Clamp(FMath::FloorToInt(OriginCol), 0, Quads - 1);
	const int32 R0 = FMath::Clamp(FMath::FloorToInt(OriginRow), 0, Quads - 1);
	const double Fc = OriginCol - C0;
	const double Fr = OriginRow - R0;
	auto At = [&](int32 Row, int32 Col) { return static_cast<double>(Heights[Row * Samples + Col]); };
	const double OriginHeight = (At(R0, C0) * (1 - Fc) + At(R0, C0 + 1) * Fc) * (1 - Fr) + (At(R0 + 1, C0) * (1 - Fc) + At(R0 + 1, C0 + 1) * Fc) * Fr;
	const float OriginOffsetCm = (static_cast<float>(OriginHeight) - 32768.0f) * ZScale / 128.0f;
	const FVector Location(-OriginCol * XYScale, -OriginRow * XYScale, OriginGroundZCm - OriginOffsetCm);

	ALandscape* Landscape = World->SpawnActor<ALandscape>(Location, FRotator::ZeroRotator);
	if (!Landscape)
	{
		return nullptr;
	}
	Landscape->SetActorScale3D(FVector(XYScale, XYScale, ZScale));
	const FGuid LandscapeGuid = FGuid::NewGuid();
	Landscape->SetLandscapeGuid(LandscapeGuid);
	if (Material)
	{
		Landscape->LandscapeMaterial = Material; // Before Import, so that the components' material instances are made from it
	}

	constexpr int32 SubsectionSizeQuads = 63;
	constexpr int32 NumSubsections = 2;
	TMap<FGuid, TArray<uint16>> HeightData;
	HeightData.Add(FGuid(), MoveTemp(Heights));
	TMap<FGuid, TArray<FLandscapeImportLayerInfo>> LayerData;
	LayerData.Add(FGuid(), TArray<FLandscapeImportLayerInfo>());
	Landscape->Import(LandscapeGuid, 0, 0, Quads, Quads, NumSubsections, SubsectionSizeQuads, HeightData, nullptr, LayerData,
		ELandscapeImportAlphamapType::Layered, TArrayView<const FLandscapeLayer>());
	Landscape->CreateLandscapeInfo();
	Landscape->UpdateAllComponentMaterialInstances();
	Landscape->SetActorLabel(TEXT("GaleLandscape"));
	UE_LOG(LogRoverloom, Display, TEXT("Landscape import: %d x %d samples, XY %.1f%%, Z %.3f%%, origin at east %.1f m north %.1f m, ground z %.1f cm"), Samples, Samples, XYScale, ZScale, OriginEastM, OriginNorthM, OriginGroundZCm);
	return Landscape;
#else
	return nullptr;
#endif
}
