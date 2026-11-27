#pragma once

#include "CoreMinimal.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/CollisionProfile.h"

// One collision rule for everything placed in a race, so that a new prop, rock or stage needs no special case:
// objects are solid bodies by default and Unreal's physics resolves every contact between them and the rovers.
// - Ground: part of the ground, which wheels stand on and climb, and which blocks bodies. Rocks. (Object type
//   WorldStatic, as the Landscape.)
// - Solid: an obstacle. It blocks a rover's body and its wheels, which do not climb it. Posts, poles, cairns,
//   buildings. (Object type WorldDynamic.)
// - GroundMark: drawn on the ground and driven over, as paint would be. Pads, sand, finish squares.
// Rovers are PhysicsBody: their bodies and wheel shapes (AWheelRig::AddWheelContactShapes) meet each other and Solid
// objects; their wheel traces see only WorldStatic, the ground.
// Rocks follow the same rule by size: a stone of up to MinSolidRockRadiusM is part of the ground's roughness, a larger
// one is Ground with the collision of its own mesh asset (scripts/unreal/build_rock_collision.py).
// Missions keep their earlier collision; this applies where a race asks for it.
namespace RoverloomCollision
{
	enum class EKind : uint8
	{
		Ground,
		Solid,
		GroundMark,
	};

	inline constexpr double MinSolidRockRadiusM = 0.15;

	// Half the width of the race track: cairns mark its edges and no stone lies inside it (plus 0.3 m). With physical
	// rovers the track must hold a rover on the line and one overtaking it; at 2.4 m, rivals were caught between a slow
	// rover and the cairns (Mac run, 2026-11-28).
	inline constexpr double RaceTrackHalfWidthM = 4.2;

	inline void Apply(UPrimitiveComponent* Component, EKind Kind)
	{
		if (!Component)
		{
			return;
		}
		if (Kind == EKind::Ground || Kind == EKind::Solid)
		{
			Component->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
			Component->SetCollisionObjectType(Kind == EKind::Solid ? ECC_WorldDynamic : ECC_WorldStatic);
			Component->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		}
		else
		{
			Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Component->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
		}
	}
}
