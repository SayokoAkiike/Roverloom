#pragma once

#include "CoreMinimal.h"

class UStaticMesh;
class UStaticMeshComponent;

// The V2 rover meshes (scripts/blender/build_rover.py, imported under /Game/Rover), for drawing a rover. Visual only.
namespace RoverloomModelV2
{
	struct FMeshes
	{
		UStaticMesh* Body = nullptr;
		UStaticMesh* Wheel = nullptr;
		UStaticMesh* Strut = nullptr;
		UStaticMesh* Axle = nullptr;
	};
	// Struts run inboard of the wheels, at build_rover.py's ARM_Y (0.877 m).
	constexpr double ArmYCm = 87.7;
	// False when the meshes are missing or -RoverModel=greybox asks for the basic shapes.
	bool Load(FMeshes& Out);
	// The body's panel colour: the "Paint" parameter of its painted slot (build_rover_materials.py). A body still on the
	// flat import material has no such parameter and keeps its colour.
	void PaintBody(UStaticMeshComponent* Body, const FLinearColor& Color);
	// Mirror the axle mesh so it runs from the wheel toward the body on either side.
	FVector AxleScale(const UStaticMesh* Axle, double MountY);
}
