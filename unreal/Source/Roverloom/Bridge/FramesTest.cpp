#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

#include "Frames.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	FVector ReadVector(const TSharedPtr<FJsonObject>& Object, const FString& Field)
	{
		const TArray<TSharedPtr<FJsonValue>>& Values = Object->GetArrayField(Field);
		return FVector(Values[0]->AsNumber(), Values[1]->AsNumber(), Values[2]->AsNumber());
	}

	FQuat ReadQuat(const TSharedPtr<FJsonObject>& Object, const FString& Field)
	{
		const TArray<TSharedPtr<FJsonValue>>& Values = Object->GetArrayField(Field);
		return FQuat(Values[0]->AsNumber(), Values[1]->AsNumber(), Values[2]->AsNumber(), Values[3]->AsNumber());
	}
}

// Every site-to-Unreal vector in schemas/conformance/frame_vectors.json, both ways. The NED columns are not ported.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRoverloomFramesGoldenTest, "Roverloom.Bridge.Frames.GoldenVectors",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRoverloomFramesGoldenTest::RunTest(const FString& Parameters)
{
	const FString Path = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir() / TEXT("../schemas/conformance/frame_vectors.json"));
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *Path))
	{
		AddError(FString::Printf(TEXT("Cannot read %s; run from a repository checkout"), *Path));
		return false;
	}
	TSharedPtr<FJsonObject> Root;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		AddError(TEXT("frame_vectors.json is not valid JSON"));
		return false;
	}
	const double Tolerance = 1e-9;
	int32 Checked = 0;
	for (const TSharedPtr<FJsonValue>& Value : Root->GetArrayField(TEXT("position")))
	{
		const TSharedPtr<FJsonObject> Case = Value->AsObject();
		const FVector Site = ReadVector(Case, TEXT("site_m"));
		const FVector Unreal = ReadVector(Case, TEXT("unreal_cm"));
		TestTrue(TEXT("site to Unreal position"), RoverloomFrames::SiteToUnrealPosition(Site).Equals(Unreal, Tolerance));
		TestTrue(TEXT("Unreal to site position"), RoverloomFrames::UnrealToSitePosition(Unreal).Equals(Site, Tolerance));
		++Checked;
	}
	for (const TSharedPtr<FJsonValue>& Value : Root->GetArrayField(TEXT("yaw")))
	{
		const TSharedPtr<FJsonObject> Case = Value->AsObject();
		const double Site = Case->GetNumberField(TEXT("site_yaw_rad"));
		const double Unreal = Case->GetNumberField(TEXT("unreal_yaw_deg"));
		TestEqual(TEXT("site yaw to Unreal degrees"), RoverloomFrames::SiteYawToUnrealDegrees(Site), Unreal, Tolerance);
		TestEqual(TEXT("Unreal degrees to site yaw"), RoverloomFrames::UnrealYawDegreesToSite(Unreal), Site, Tolerance);
		++Checked;
	}
	for (const TSharedPtr<FJsonValue>& Value : Root->GetArrayField(TEXT("quaternion")))
	{
		const TSharedPtr<FJsonObject> Case = Value->AsObject();
		const FQuat Site = ReadQuat(Case, TEXT("site_xyzw"));
		const FQuat Unreal = ReadQuat(Case, TEXT("unreal_xyzw"));
		// Component-wise, not up to sign: the vectors fix the sign as Python computes it.
		const FQuat Converted = RoverloomFrames::SiteToUnrealQuat(Site);
		TestTrue(TEXT("site to Unreal quaternion"), FMath::Abs(Converted.X - Unreal.X) <= Tolerance && FMath::Abs(Converted.Y - Unreal.Y) <= Tolerance
			&& FMath::Abs(Converted.Z - Unreal.Z) <= Tolerance && FMath::Abs(Converted.W - Unreal.W) <= Tolerance);
		++Checked;
	}
	TestTrue(TEXT("vectors were checked"), Checked > 0);
	AddInfo(FString::Printf(TEXT("%d golden cases checked"), Checked));
	return true;
}

#endif
