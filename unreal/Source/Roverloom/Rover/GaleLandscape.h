#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"

#include "GaleLandscape.generated.h"

class ALandscape;
class UMaterialInterface;
class UWorld;

// Editor-only: builds a Landscape from a raw r16 heightfield (see scripts/terrain/hirise_site.py). It exists so that
// Editor Python can make the Gale level once; the game only loads the saved level. Outside the editor it returns null.
// Visual terrain only: it sets no collision or physics values, and the rover's drive code is untouched.
UCLASS()
class URoverloomLandscapeLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	// Samples must be a valid Landscape size (1009 = 8 x 8 components of 2 x 63 quads, plus one). The r16 is unsigned
	// 16-bit little-endian, row 0 north. XYScalePercent is 100 for 1 m posts. ZScalePercent is 100 for a 512 m span, as in
	// gale_site.json. The point OriginEastM, OriginNorthM from the Landscape's center (contract frame, meters) is put at the
	// world origin, with its ground at OriginGroundZCm, so the rover starts at the site origin on whatever patch is chosen.
	UFUNCTION(BlueprintCallable, Category = "Roverloom")
	static ALandscape* ImportR16Landscape(UWorld* World, const FString& R16Path, int32 Samples, float XYScalePercent,
		float ZScalePercent, float OriginEastM, float OriginNorthM, float OriginGroundZCm, UMaterialInterface* Material);
};
