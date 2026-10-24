#pragma once
#include <sofa/component/solidmechanics/fem/elastic/TetrahedronFEMForceField.h>
#include <sofa/core/behavior/BaseLocalForceFieldMatrix.h>

// The SOFA 26.06 corotational force/strain/rotation implementation is retained.
// Only the equivalent stiffness assembly is specialized: diag(R,R,R,R) * K *
// diag(R^T,R^T,R^T,R^T) is evaluated as sixteen 3x3 block products. This avoids
// multiplying the many known zeros in two dense 12x12 products. All sixteen
// coupling blocks are still assembled, in the original element/node order.
class Phase6FEM : public sofa::component::solidmechanics::fem::elastic::TetrahedronFEMForceField<sofa::defaulttype::Vec3Types> {
public:
    using Base=sofa::component::solidmechanics::fem::elastic::TetrahedronFEMForceField<sofa::defaulttype::Vec3Types>;
    SOFA_CLASS(Phase6FEM,Base);
    Phase6FEM()=default;
    using Mat3=sofa::type::Mat<3,3,double>;
    StiffnessMatrix elementMatrix(size_t id){
        sofa::type::MatNoInit<6,12,double> transpose;transpose.transpose(strainDisplacements[id]);
        StiffnessMatrix local=strainDisplacements[id]*materialsStiffnesses[id]*transpose;
        if(method==SMALL)return local;
        const auto&rotation=rotations[id];Mat3 rt;rt.transpose(rotation);StiffnessMatrix result;
        for(int a=0;a<4;a++)for(int b=0;b<4;b++){
            Mat3 block;local.getsub(a*3,b*3,block);const Mat3 rotated=(rotation*block)*rt;
            for(int r=0;r<3;r++)for(int c=0;c<3;c++)result(a*3+r,b*3+c)=rotated(r,c);
        }return result;
    }
    void buildStiffnessMatrix(sofa::core::behavior::StiffnessMatrix* matrix)override{
        auto derivative=matrix->getForceDerivativeIn(this->mstate).withRespectToPositionsIn(this->mstate);
        for(size_t id=0;id<_indexedElements->size();id++){
            const auto&element=(*_indexedElements)[id];const auto stiffness=elementMatrix(id);
            for(int a=0;a<4;a++)for(int b=0;b<4;b++){
                Mat3 block;stiffness.getsub(a*3,b*3,block);derivative(element[a]*3,element[b]*3)+=-block;
            }
        }
    }
    std::pair<double,double> compareWithSofaReference(){
        double maximumAbsolute=0,maximumRelative=0;
        for(size_t id=0;id<_indexedElements->size();id++){
            Transformation rotation;if(method==SMALL)rotation.identity();else rotation=rotations[id];
            StiffnessMatrix first,reference;computeStiffnessMatrix(first,reference,materialsStiffnesses[id],strainDisplacements[id],rotation);
            const auto optimized=elementMatrix(id);double scale=0,error=0;
            for(int r=0;r<12;r++)for(int c=0;c<12;c++){scale=std::max(scale,std::abs(reference(r,c)));error=std::max(error,std::abs(reference(r,c)-optimized(r,c)));}
            maximumAbsolute=std::max(maximumAbsolute,error);maximumRelative=std::max(maximumRelative,error/std::max(1.,scale));
        }return {maximumAbsolute,maximumRelative};
    }
};
