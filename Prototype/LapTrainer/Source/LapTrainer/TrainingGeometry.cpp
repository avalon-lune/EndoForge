#include "TrainingGeometry.h"

namespace
{
    void Quad(FTrainingRenderMesh& M, FVector A, FVector B, FVector C, FVector D, const FVector& Outward)
    {
        if (FVector::DotProduct(FVector::CrossProduct(B - A, C - A), Outward) < 0.0) Swap(B, D);
        const FVector N = FVector::CrossProduct(B - A, C - A).GetSafeNormal();
        const int32 I = M.Positions.Num();
        M.Positions.Append({ A, B, C, D });
        M.Normals.Append({ N, N, N, N });
        M.UV.Append({ FVector2D(A.X, A.Y), FVector2D(B.X, B.Y), FVector2D(C.X, C.Y), FVector2D(D.X, D.Y) });
        M.Triangles.Append({ I, I + 2, I + 1, I, I + 3, I + 2 });
    }

    TArray<FVector2D> CrossSection(double HY, double HZ, double Bevel)
    {
        return { FVector2D(-HY + Bevel, -HZ), FVector2D(HY - Bevel, -HZ),
            FVector2D(HY, -HZ + Bevel), FVector2D(HY, HZ - Bevel),
            FVector2D(HY - Bevel, HZ), FVector2D(-HY + Bevel, HZ),
            FVector2D(-HY, HZ - Bevel), FVector2D(-HY, -HZ + Bevel) };
    }

    void Complete(FTrainingRenderMesh& M)
    {
        M.Colors.Init(FLinearColor::White, M.Positions.Num());
        M.Tangents.SetNum(M.Positions.Num());
        for (int32 I = 0; I < M.Normals.Num(); ++I)
        {
            FVector T = FVector::ForwardVector - M.Normals[I] * M.Normals[I].X;
            if (!T.Normalize()) T = FVector::RightVector;
            M.Tangents[I] = FProcMeshTangent(T, false);
        }
    }

    FTrainingRenderMesh BeveledBody(const FVector& H, double B, int32 OmittedInnerSide)
    {
        FTrainingRenderMesh M;
        const TArray<FVector2D> Outer = CrossSection(H.Y, H.Z, B);
        const TArray<FVector2D> End = CrossSection(H.Y - B, H.Z - B, B * 0.4);
        TArray<TArray<FVector>> Rings;
        for (int32 R = 0; R < 4; ++R)
        {
            const double X = R == 0 ? -H.X : R == 1 ? -H.X + B : R == 2 ? H.X - B : H.X;
            const TArray<FVector2D>& Profile = R == 0 || R == 3 ? End : Outer;
            TArray<FVector> Ring;
            for (const FVector2D& P : Profile) Ring.Add(FVector(X, P.X, P.Y));
            Rings.Add(MoveTemp(Ring));
        }
        for (int32 R = 0; R < 3; ++R)
        {
            for (int32 I = 0; I < 8; ++I)
            {
                const int32 J = (I + 1) % 8;
                // The serrated surface replaces only the central flat inner face.
                if (R == 1 && ((OmittedInnerSide < 0 && I == 0) || (OmittedInnerSide > 0 && I == 4))) continue;
                FVector N(0, (Rings[R][I].Y + Rings[R][J].Y) * 0.5,
                    (Rings[R][I].Z + Rings[R][J].Z) * 0.5);
                if (R == 0) N.X = -B * 4;
                if (R == 2) N.X = B * 4;
                Quad(M, Rings[R][I], Rings[R + 1][I], Rings[R + 1][J], Rings[R][J], N);
            }
        }
        for (const int32 R : { 0, 3 })
        {
            const FVector Center(R == 0 ? -H.X : H.X, 0, 0);
            for (int32 I = 0; I < 8; ++I)
            {
                const int32 J = (I + 1) % 8;
                const FVector N(R == 0 ? -1 : 1, 0, 0);
                Quad(M, Center, Rings[R][I], Rings[R][J], Center, N);
            }
        }
        Complete(M);
        return M;
    }

    FVector PNEdge(const FVector& A, const FVector& B, const FVector& N)
    {
        return (A * 2.0 + B - FVector::DotProduct(B - A, N) * N) / 3.0;
    }
}

FTrainingRenderMesh TrainingGeometry::MakeBeveledBox(const FVector& HalfExtent, float BevelCm)
{
    return BeveledBody(HalfExtent, FMath::Clamp(static_cast<double>(BevelCm), 0.001, HalfExtent.GetMin() * 0.8), 0);
}

FTrainingRenderMesh TrainingGeometry::MakeSerratedJaw(int32 JawSign)
{
    const FVector H(0.725, 0.125, 0.070);
    constexpr double B = 0.008;
    const int32 InnerSide = -JawSign;
    FTrainingRenderMesh M = BeveledBody(H, B, InnerSide);
    constexpr int32 NX = 96, NY = 18;
    auto Height = [&](double X, double Y)
    {
        // Real geometry, not a normal-map stand-in: transverse serrations plus a shallow
        // longitudinal drainage groove. Valleys recede from the collision envelope.
        const double EdgeFade = FMath::Clamp((H.X - B - FMath::Abs(X)) / 0.08, 0.0, 1.0) *
            FMath::Clamp((H.Y - B - FMath::Abs(Y)) / 0.025, 0.0, 1.0);
        const double Phase = FMath::Frac((X + H.X) / 0.115);
        const double Serration = 0.0055 * (1.0 - FMath::Abs(Phase * 2.0 - 1.0));
        const double Channel = 0.0070 * FMath::Clamp(1.0 - FMath::Abs(Y) / 0.027, 0.0, 1.0);
        const double Recess = FMath::Min(0.0095, Serration + Channel) * EdgeFade;
        return InnerSide * (H.Z - Recess);
    };
    const int32 First = M.Positions.Num();
    for (int32 IX = 0; IX <= NX; ++IX)
    {
        const double X = FMath::Lerp(-H.X + B, H.X - B, static_cast<double>(IX) / NX);
        for (int32 IY = 0; IY <= NY; ++IY)
        {
            const double Y = FMath::Lerp(-H.Y + B, H.Y - B, static_cast<double>(IY) / NY);
            const double DX = (Height(X + 0.0005, Y) - Height(X - 0.0005, Y)) / 0.001;
            const double DY = (Height(X, Y + 0.0005) - Height(X, Y - 0.0005)) / 0.001;
            M.Positions.Add(FVector(X, Y, Height(X, Y)));
            M.Normals.Add((FVector(-DX, -DY, 1) * InnerSide).GetSafeNormal());
            M.UV.Add(FVector2D((X + H.X) / (2 * H.X), (Y + H.Y) / (2 * H.Y)));
        }
    }
    for (int32 IX = 0; IX < NX; ++IX)
    {
        for (int32 IY = 0; IY < NY; ++IY)
        {
            const int32 A = First + IX * (NY + 1) + IY, BB = A + NY + 1, C = BB + 1, D = A + 1;
            if (InnerSide > 0) M.Triangles.Append({ A, C, BB, A, D, C });
            else M.Triangles.Append({ A, BB, C, A, C, D });
        }
    }
    Complete(M);
    return M;
}

void TrainingGeometry::BuildSurfaceBindings(const TArray<FVector>& RestPositions, const TArray<int32>& Faces,
    int32 Subdivisions, TArray<FTrainingSurfaceSample>& OutSamples, FTrainingRenderMesh& OutMesh)
{
    OutSamples.Reset();
    OutMesh = FTrainingRenderMesh();
    const int32 S = FMath::Clamp(Subdivisions, 1, 5);
    for (int32 Face = 0; Face + 2 < Faces.Num(); Face += 3)
    {
        const int32 A = Faces[Face], B = Faces[Face + 1], C = Faces[Face + 2];
        if (!RestPositions.IsValidIndex(A) || !RestPositions.IsValidIndex(B) || !RestPositions.IsValidIndex(C)) continue;
        const int32 Base = OutSamples.Num();
        auto Index = [S, Base](int32 I, int32 J) { return Base + I * (S + 1) - I * (I - 1) / 2 + J; };
        for (int32 I = 0; I <= S; ++I)
        {
            for (int32 J = 0; J <= S - I; ++J)
            {
                const FVector W(1.0 - static_cast<double>(I + J) / S, static_cast<double>(I) / S, static_cast<double>(J) / S);
                OutSamples.Add({ A, B, C, W });
                const FVector P = RestPositions[A] * W.X + RestPositions[B] * W.Y + RestPositions[C] * W.Z;
                OutMesh.Positions.Add(P);
                OutMesh.UV.Add(FVector2D((P.X + 6.0) / 12.0, (P.Y + 4.0) / 8.0));
                OutMesh.Normals.Add(FVector::UpVector);
            }
        }
        for (int32 I = 0; I < S; ++I)
        {
            for (int32 J = 0; J < S - I; ++J)
            {
                // Reverse SOFA's right-handed face winding for UE front-face rasterisation.
                OutMesh.Triangles.Append({ Index(I, J), Index(I, J + 1), Index(I + 1, J) });
                if (I + J < S - 1)
                    OutMesh.Triangles.Append({ Index(I + 1, J), Index(I, J + 1), Index(I + 1, J + 1) });
            }
        }
    }
    Complete(OutMesh);
}

void TrainingGeometry::UpdateBoundSurface(const TArray<FVector>& Positions, const TArray<FVector>& Normals,
    const TArray<FTrainingSurfaceSample>& Samples, FTrainingRenderMesh& Mesh, double MaxSurfaceOffsetCm)
{
    for (int32 I = 0; I < Samples.Num(); ++I)
    {
        const FTrainingSurfaceSample& S = Samples[I];
        const FVector& A = Positions[S.A]; const FVector& B = Positions[S.B]; const FVector& C = Positions[S.C];
        const FVector& NA = Normals[S.A]; const FVector& NB = Normals[S.B]; const FVector& NC = Normals[S.C];
        const double U = S.Weight.X, V = S.Weight.Y, W = S.Weight.Z;
        const FVector EAB = PNEdge(A, B, NA), EBA = PNEdge(B, A, NB), EAC = PNEdge(A, C, NA);
        const FVector ECA = PNEdge(C, A, NC), EBC = PNEdge(B, C, NB), ECB = PNEdge(C, B, NC);
        const FVector E = (EAB + EBA + EAC + ECA + EBC + ECB) / 6.0;
        const FVector Center = E + (E - (A + B + C) / 3.0) * 0.5;
        const FVector PN = A * (U * U * U) + B * (V * V * V) + C * (W * W * W) +
            3.0 * (EAB * (U * U * V) + EBA * (U * V * V) + EAC * (U * U * W) +
                ECA * (U * W * W) + EBC * (V * V * W) + ECB * (V * W * W)) + Center * (6.0 * U * V * W);
        const FVector Linear = A * U + B * V + C * W;
        Mesh.Positions[I] = Linear + (PN - Linear).GetClampedToMaxSize(MaxSurfaceOffsetCm);
        const FVector N = (NA * U + NB * V + NC * W).GetSafeNormal(UE_SMALL_NUMBER, FVector::UpVector);
        Mesh.Normals[I] = N;
        FVector T = FVector::ForwardVector - N * N.X;
        if (!T.Normalize()) T = FVector::RightVector;
        Mesh.Tangents[I] = FProcMeshTangent(T, false);
    }
}
