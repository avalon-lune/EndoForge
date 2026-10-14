#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <mmsystem.h>
#include <sofa/simulation/graph/init.h>
#include <sofa/simulation/graph/DAGSimulation.h>
#include <sofa/simulation/Node.h>
#include <sofa/simulation/Simulation.h>
#include <sofa/core/ObjectFactory.h>
#include <sofa/core/objectmodel/BaseObjectDescription.h>
#include <sofa/helper/system/PluginManager.h>
#include <sofa/helper/system/FileRepository.h>
#include <sofa/component/statecontainer/MechanicalObject.h>
#include <sofa/defaulttype/VecTypes.h>
#include <nlohmann/json.hpp>
#include <array>
#include <atomic>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <thread>
#include <vector>

using json=nlohmann::json;
using V=sofa::defaulttype::Vec3Types::Coord;
using MO=sofa::component::statecontainer::MechanicalObject<sofa::defaulttype::Vec3Types>;
using Clock=std::chrono::steady_clock;
using Obj=sofa::core::objectmodel::BaseComponent::SPtr;
constexpr double Dt=1.0/30.0;
std::atomic_bool running=true;
BOOL WINAPI ctrl(DWORD){running=false; return TRUE;}
double length(const V& v){return std::sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);}
std::string vecText(const std::vector<V>& a){std::ostringstream s; s<<std::setprecision(15);for(auto&v:a)s<<v[0]<<' '<<v[1]<<' '<<v[2]<<' ';return s.str();}
template<class T>std::string indices(const T& a){std::ostringstream s;for(auto&v:a)s<<v<<' ';return s.str();}
Obj add(sofa::simulation::Node* node,const char* type,std::initializer_list<std::pair<const char*,std::string>> attrs={}){
    sofa::core::objectmodel::BaseObjectDescription desc(type,type);
    for(auto&[k,v]:attrs)desc.setAttribute(k,v.c_str());
    auto o=sofa::core::ObjectFactory::getInstance()->createObject(node,&desc);
    if(!o){for(auto&e:desc.getErrors())std::cerr<<e<<std::endl;throw std::runtime_error(std::string("Cannot construct ")+type);}
    return o;
}
void field(Obj o,const char*n,const std::string&v){auto*d=o->findData(n);if(!d||!d->read(v))throw std::runtime_error(std::string("Cannot set ")+n);}

#include "Phase2Model.h"
#include "Phase3Model.h"

int serve(Tissue&t,int port){
    WSADATA data;WSAStartup(MAKEWORD(2,2),&data);SOCKET listener=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);sockaddr_in a{};a.sin_family=AF_INET;a.sin_port=htons(u_short(port));inet_pton(AF_INET,"127.0.0.1",&a.sin_addr);
    if(bind(listener,(sockaddr*)&a,sizeof(a))||listen(listener,1)){std::cerr<<"Cannot listen on localhost port "<<port<<" error "<<WSAGetLastError()<<std::endl;return 3;}
    u_long nonblock=1;ioctlsocket(listener,FIONBIO,&nonblock);SOCKET client=INVALID_SOCKET;std::string input,output;size_t sent=0;auto lastCommand=Clock::now();auto next=Clock::now();
    std::cout<<"READY SOFA 26.06 FEM localhost:"<<port<<" nodes="<<t.rest.size()<<" tets="<<t.tets.size()<<std::endl;
    timeBeginPeriod(1);SetConsoleCtrlHandler(ctrl,TRUE);
    while(running){
        if(client==INVALID_SOCKET){client=accept(listener,nullptr,nullptr);if(client!=INVALID_SOCKET){t.reset(0);ioctlsocket(client,FIONBIO,&nonblock);BOOL one=TRUE;setsockopt(client,IPPROTO_TCP,TCP_NODELAY,(char*)&one,sizeof(one));input.clear();output=t.hello().dump()+"\n";sent=0;lastCommand=Clock::now();std::cout<<"Client connected"<<std::endl;}}
        bool disconnected=false;
        if(client!=INVALID_SOCKET){
            char buf[8192];for(int i=0;i<32;i++){int n=recv(client,buf,sizeof(buf),0);if(n>0)input.append(buf,n);else{if(n==0||(n<0&&WSAGetLastError()!=WSAEWOULDBLOCK))disconnected=true;break;}}
            size_t pos;int processed=0;
            while(processed<64&&(pos=input.find('\n'))!=std::string::npos){
                if(pos>4096){disconnected=true;break;}
                auto line=input.substr(0,pos);input.erase(0,pos+1);processed++;
                try{if(t.command(json::parse(line)))lastCommand=Clock::now();}catch(const std::exception&){t.message="Invalid command ignored";}
            }
            if(input.size()>262144||(input.find('\n')==std::string::npos&&input.size()>4096))disconnected=true;
        }
        if(std::chrono::duration<double>(Clock::now()-lastCommand).count()>.5){t.closed=0;t.commanded=t.tip;if(t.grasping)t.release("Input timeout - released");}
        t.step();
        if(client!=INVALID_SOCKET&&!disconnected){
            if(output.empty()){output=t.state().dump()+"\n";sent=0;}
            if(!output.empty()){int n=send(client,output.data()+sent,int(output.size()-sent),0);if(n>0){sent+=n;if(sent==output.size())output.clear();}else if(WSAGetLastError()!=WSAEWOULDBLOCK)disconnected=true;}
        }
        if(disconnected){closesocket(client);client=INVALID_SOCKET;input.clear();output.clear();t.closed=0;t.release("Client disconnected - released");}
        next+=std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(Dt));auto now=Clock::now();if(next<now-std::chrono::milliseconds(50))next=now;std::this_thread::sleep_until(next);
    }
    if(client!=INVALID_SOCKET)closesocket(client);closesocket(listener);WSACleanup();timeEndPeriod(1);return 0;
}

int servePhase3(Membrane&t,int port){
    WSADATA data;WSAStartup(MAKEWORD(2,2),&data);SOCKET listener=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);sockaddr_in a{};a.sin_family=AF_INET;a.sin_port=htons(u_short(port));inet_pton(AF_INET,"127.0.0.1",&a.sin_addr);
    if(bind(listener,(sockaddr*)&a,sizeof(a))||listen(listener,1)){std::cerr<<"Cannot listen localhost:"<<port<<std::endl;return 3;}
    u_long nonblock=1;ioctlsocket(listener,FIONBIO,&nonblock);SOCKET client=INVALID_SOCKET;std::string input,output;size_t sent=0;auto lastCommand=Clock::now(),next=Clock::now();bool timedOut=false;
    std::cout<<"READY Phase3 SOFA membrane localhost:"<<port<<" nodes="<<t.rest.size()<<" faces="<<t.triangles.size()<<std::endl;timeBeginPeriod(1);SetConsoleCtrlHandler(ctrl,TRUE);
    while(running){
        if(client==INVALID_SOCKET){client=accept(listener,nullptr,nullptr);if(client!=INVALID_SOCKET){t.reset(0);ioctlsocket(client,FIONBIO,&nonblock);BOOL one=TRUE;setsockopt(client,IPPROTO_TCP,TCP_NODELAY,(char*)&one,sizeof(one));input.clear();output=t.hello().dump()+"\n";sent=0;lastCommand=Clock::now();timedOut=false;}}
        bool disconnected=false;if(client!=INVALID_SOCKET){char buf[8192];for(int i=0;i<32;i++){int n=recv(client,buf,sizeof(buf),0);if(n>0)input.append(buf,n);else{if(n==0||(n<0&&WSAGetLastError()!=WSAEWOULDBLOCK))disconnected=true;break;}}
            size_t pos;int processed=0;while(processed<64&&(pos=input.find('\n'))!=std::string::npos){if(pos>4096){disconnected=true;break;}auto line=input.substr(0,pos);input.erase(0,pos+1);processed++;try{if(t.command(json::parse(line))){lastCommand=Clock::now();timedOut=false;}}catch(const std::exception&){t.message="Invalid command ignored";}}
            if(input.size()>262144||(input.find('\n')==std::string::npos&&input.size()>4096))disconnected=true;
        }
        if(!timedOut&&std::chrono::duration<double>(Clock::now()-lastCommand).count()>.5){t.stopInput("Input timeout - both tools released");timedOut=true;}t.step();
        if(client!=INVALID_SOCKET&&!disconnected){if(output.empty()){output=t.state().dump()+"\n";sent=0;}int n=send(client,output.data()+sent,int(output.size()-sent),0);if(n>0){sent+=n;if(sent==output.size())output.clear();}else if(WSAGetLastError()!=WSAEWOULDBLOCK)disconnected=true;}
        if(disconnected){closesocket(client);client=INVALID_SOCKET;input.clear();output.clear();t.stopInput("Client disconnected - both tools released");}
        next+=std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(Dt));auto now=Clock::now();if(next<now-std::chrono::milliseconds(50))next=now;std::this_thread::sleep_until(next);
    }
    if(client!=INVALID_SOCKET)closesocket(client);closesocket(listener);WSACleanup();timeEndPeriod(1);return 0;
}

int main(int argc,char**argv){
    try{
        const auto exe=std::filesystem::absolute(argv[0]).parent_path();std::filesystem::current_path(exe);
        sofa::simulation::graph::init();
        auto&pm=sofa::helper::system::PluginManager::getInstance();
        const char*plugins[]={"Sofa.Component.AnimationLoop","Sofa.Component.StateContainer","Sofa.Component.Topology.Container.Dynamic","Sofa.Component.Topology.Container.Constant","Sofa.Component.ODESolver.Backward","Sofa.Component.LinearSolver.Iterative","Sofa.Component.LinearSolver.Direct","Sofa.Component.Mass","Sofa.Component.MechanicalLoad","Sofa.Component.SolidMechanics.FEM.Elastic","Sofa.Component.SolidMechanics.Spring","Sofa.Component.Constraint.Projective","Sofa.Component.Constraint.Lagrangian.Solver","Sofa.Component.Constraint.Lagrangian.Model","Sofa.Component.Constraint.Lagrangian.Correction","Sofa.Component.Collision.Detection.Algorithm","Sofa.Component.Collision.Detection.Intersection","Sofa.Component.Collision.Geometry","Sofa.Component.Collision.Response.Contact","Sofa.Component.Mapping.Linear","Sofa.Component.Mapping.NonLinear"};
        for(auto*p:plugins){pm.loadPlugin((exe/(std::string(p)+".dll")).generic_string());sofa::core::ObjectFactory::getInstance()->registerObjectsFromPlugin(p);}
        int result;
        {
            bool phase2=false,self2=false,self3=false;int port=0;std::filesystem::path report;
            for(int i=1;i<argc;i++){std::string arg=argv[i];if(arg=="--phase2")phase2=true;else if(arg=="--port"&&i+1<argc)port=std::stoi(argv[++i]);else if(arg=="--self-test"||arg=="--self-test-phase3"){self2=arg=="--self-test";self3=!self2;if(i+1<argc)report=argv[++i];}}
            if(phase2||self2){Tissue tissue;result=self2?selfTest(tissue,report.empty()?"phase2-physics-test-results.json":report):serve(tissue,port?port:47322);}
            else{Membrane tissue;result=self3?selfTestPhase3(tissue,report.empty()?"phase3-physics-test-results.json":report):servePhase3(tissue,port?port:47323);}
        }
        sofa::simulation::Simulation::theSimulation.reset();
        sofa::simulation::graph::cleanup();
        return result;
    }catch(const std::exception&e){std::cerr<<"FATAL "<<e.what()<<std::endl;return 1;}
}
