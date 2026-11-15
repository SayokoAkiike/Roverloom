#pragma once

#include "CoreMinimal.h"

class UStaticMeshComponent;

// Flat colors for engine basic shapes, with no project asset.
namespace RoverloomGreybox
{
	// In UE 5.8.4 the engine's Cube uses WorldGridMaterial, and Sphere and Cylinder use DefaultMaterial. Neither has a
	// color parameter, so a dynamic instance of the mesh's own material ignores any color. This makes the instance from
	// BasicShapeMaterial, which has the vector parameter "Color" and the scalar "Roughness".
	void Paint(UStaticMeshComponent* Mesh, const FLinearColor& Color, float Roughness = 0.8f);
}
