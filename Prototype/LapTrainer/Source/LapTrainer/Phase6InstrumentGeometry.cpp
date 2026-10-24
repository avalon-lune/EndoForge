#include "Phase6InstrumentGeometry.h"

namespace
{
double Fade(double Value, double Width)
{
    const double T = FMath::Clamp(Value / Width, 0.0, 1.0);
    return T * T * (3.0 - 2.0 * T);
}

double Recess(double X, double Y, const FVector& H, double Radius, bool bInner)
{
    const double Mask = Fade(H.X - Radius - FMath::Abs(X), .055) *
        Fade(H.Y - Radius - FMath::Abs(Y), .022);
    if (bInner)
    {
        // Tapered real transverse teeth. All valleys recede into the existing
        // box, so a bright line cannot imply a protruding physical tooth.
        const double Phase = FMath::Frac((X + H.X) / .115);
        const double Tooth = .0058 * (1.0 - FMath::Abs(2.0 * Phase - 1.0));
        const double Channel = .0050 * FMath::Exp(-FMath::Square(Y / .026));
        return FMath::Min(.0085, Tooth + Channel) * Mask;
    }
    // Shallow machining relief on the back, never a through-hole. This also
    // provides a gradual highlight across the formerly flat rectangular face.
    return .0024 * FMath::Exp(-FMath::Square(Y / .052)) * Mask;
}

void AddTriangle(FTrainingRenderMesh& M, int32 A, int32 B, int32 C)
{
    const FVector Outward = M.Normals[A] + M.Normals[B] + M.Normals[C];
    const FVector Cross = FVector::CrossProduct(M.Positions[B] - M.Positions[A], M.Positions[C] - M.Positions[A]);
    // Front-face winding is clockwise in UE while normals stay outward.
    if (FVector::DotProduct(Cross, Outward) > 0) M.Triangles.Append({A, C, B});
    else M.Triangles.Append({A, B, C});
}

FTrainingRenderMesh RoundedBody(const FVector& H, double Radius, const FIntVector& Divisions, int32 InnerSign)
{
    FTrainingRenderMesh M;
    const FVector Core = H - FVector(Radius);
    for (int32 Axis = 0; Axis < 3; ++Axis)
    {
        const int32 U = (Axis + 1) % 3, V = (Axis + 2) % 3;
        const int32 NU = Divisions[U], NV = Divisions[V];
        for (int32 Sign : {-1, 1})
        {
            const int32 First = M.Positions.Num();
            for (int32 I = 0; I <= NU; ++I)
            {
                for (int32 J = 0; J <= NV; ++J)
                {
                    FVector Box = FVector::ZeroVector;
                    Box[Axis] = Sign * H[Axis];
                    Box[U] = FMath::Lerp(-H[U], H[U], double(I) / NU);
                    Box[V] = FMath::Lerp(-H[V], H[V], double(J) / NV);
                    FVector C;
                    for (int32 K = 0; K < 3; ++K) C[K] = FMath::Clamp(Box[K], -Core[K], Core[K]);
                    FVector N = (Box - C).GetSafeNormal();
                    FVector P = C + N * Radius;
                    if (InnerSign && Axis == 2)
                    {
                        const bool bInner = Sign == InnerSign;
                        const double Depth = Recess(P.X, P.Y, H, Radius, bInner);
                        if (Depth > 1.e-12)
                        {
                            constexpr double D = .00005;
                            const double DX = (Recess(P.X + D, P.Y, H, Radius, bInner) - Recess(P.X - D, P.Y, H, Radius, bInner)) / (2 * D);
                            const double DY = (Recess(P.X, P.Y + D, H, Radius, bInner) - Recess(P.X, P.Y - D, H, Radius, bInner)) / (2 * D);
                            P.Z -= Sign * Depth;
                            N = FVector(DX, DY, Sign).GetSafeNormal();
                        }
                    }
                    M.Positions.Add(P); M.Normals.Add(N);
                    M.UV.Add(FVector2D((Box[U] + H[U]) / (2 * H[U]), (Box[V] + H[V]) / (2 * H[V])));
                }
            }
            for (int32 I = 0; I < NU; ++I)
            {
                for (int32 J = 0; J < NV; ++J)
                {
                    const int32 A = First + I * (NV + 1) + J, B = A + NV + 1, C = B + 1, D = A + 1;
                    AddTriangle(M, A, B, C); AddTriangle(M, A, C, D);
                }
            }
        }
    }
    M.Colors.Init(FLinearColor::White, M.Positions.Num());
    M.Tangents.SetNum(M.Positions.Num());
    for (int32 I = 0; I < M.Positions.Num(); ++I)
    {
        FVector T = FVector::ForwardVector - M.Normals[I] * M.Normals[I].X;
        if (!T.Normalize()) T = FVector::RightVector;
        M.Tangents[I] = FProcMeshTangent(T, false);
    }
    return M;
}
}

FTrainingRenderMesh Phase6InstrumentGeometry::MakeSerratedJaw(int32 JawSign)
{
    // A box corner to rounded-box displacement is at most R*(sqrt(3)-1)
    // = 0.132 mm. Face recesses are <=0.085 mm and vanish before rounded edges.
    return RoundedBody(FVector(.725, .125, .070), .018, FIntVector(128, 32, 24), JawSign < 0 ? 1 : -1);
}

FTrainingRenderMesh Phase6InstrumentGeometry::MakeRoundedFork()
{
    return RoundedBody(FVector(.23, .048, .22), .035, FIntVector(32, 12, 32), 0);
}

Phase6InstrumentGeometry::FJawAudit Phase6InstrumentGeometry::AuditJaw(const FTrainingRenderMesh& Mesh)
{
    FJawAudit A; A.VertexCount = Mesh.Positions.Num(); A.TriangleCount = Mesh.Triangles.Num() / 3;
    const FVector H(.725, .125, .070);
    for (const FVector& P : Mesh.Positions)
    {
        A.bFinite &= !P.ContainsNaN();
        const FVector Gap = H - P.GetAbs();
        A.bInsideCollisionEnvelope &= Gap.GetMin() >= -1.e-10;
        A.MaximumInteriorGapMm = FMath::Max(A.MaximumInteriorGapMm, Gap.GetMin() * 10.0);
    }
    for (int32 I = 0; I + 2 < Mesh.Triangles.Num(); I += 3)
    {
        const FVector& P = Mesh.Positions[Mesh.Triangles[I]], & Q = Mesh.Positions[Mesh.Triangles[I + 1]], & R = Mesh.Positions[Mesh.Triangles[I + 2]];
        if (FVector::CrossProduct(Q - P, R - P).SizeSquared() < 1.e-20) ++A.DegenerateTriangles;
    }
    return A;
}
