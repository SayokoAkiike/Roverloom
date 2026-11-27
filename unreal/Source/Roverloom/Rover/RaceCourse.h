#pragma once

#include "CoreMinimal.h"

// The race course, as Python's race.Course.document() writes it to course.json (docs/race.md). Site frame, metres.
// Unreal only draws it: Python alone judges checkpoints, laps and positions.
struct FRaceCourse
{
	FString Name;
	TArray<FVector2D> Checkpoints; // The last one is the start and finish line
	TArray<FBox2D> Sand;
	TArray<FVector2D> Pads;
	bool bHasSupply = false;
	FVector2D Supply = FVector2D::ZeroVector;
	double GateRadiusM = 2.5;
	int32 Laps = 1;

	bool IsValid() const { return Checkpoints.Num() >= 2; }
};

namespace RoverloomRace
{
	// Reads -RoverCourseFile=<path>. Returns false, and logs why, when it is absent or malformed.
	bool LoadCourse(FRaceCourse& Out);
	// Loaded once per process and shared by the game mode and the HUD.
	const FRaceCourse& Course();
}
