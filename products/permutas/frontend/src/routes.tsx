import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'

import RequireAuth from './utils/RequireAuth'
import AuthenticatedLayout from './layouts/AuthenticatedLayout'
import AuthenticatedRedirect from './utils/AuthenticatedRedirect'
import { LoadingScreen } from './components/Spinner'

const Login = lazy(() => import('./pages/Login'))
const Landing = lazy(() => import('./pages/Landing'))
const Home = lazy(() => import('./pages/Home'))

const Imoveis = lazy(() => import('./pages/Imoveis'))
const NovoImovel = lazy(() => import('./pages/Imoveis/Novo'))
const MeusImoveis = lazy(() => import('./pages/Imoveis/Meus'))
const Imovel = lazy(() => import('./pages/Imoveis/Imovel'))

const Permutas = lazy(() => import('./pages/Permutas'))
const MinhasPermutas = lazy(() => import('./pages/Permutas/Minhas'))
const NovaPermuta = lazy(() => import('./pages/Permutas/Nova'))
const PermutaImovel = lazy(() => import('./pages/Permutas/PermutaImovel'))
const PermutaAutomovel = lazy(() => import('./pages/Permutas/PermutaAutomovel'))

const Clientes = lazy(() => import('./pages/Clientes'))
const MeusClientes = lazy(() => import('./pages/Clientes/Meus'))
const NovoCliente = lazy(() => import('./pages/Clientes/Novo'))
const Cliente = lazy(() => import('./pages/Clientes/Cliente'))

const NovoCondominio = lazy(() => import('./pages/Condominios/Novo'))
const MeusCondominios = lazy(() => import('./pages/Condominios/Meus'))
const Condominios = lazy(() => import('./pages/Condominios'))
const Condominio = lazy(() => import('./pages/Condominios/Condominio'))

const Matches = lazy(() => import('./pages/Matches'))
const MatchDossie = lazy(() => import('./pages/Matches/Match'))

const Corretores = lazy(() => import('./pages/Corretores'))
const Corretor = lazy(() => import('./pages/Corretores/Corretor'))

const Rotas = () => {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<Landing />} />
        <Route
          path="/login"
          element={
            <AuthenticatedRedirect>
              <Login />
            </AuthenticatedRedirect>
          }
        />
        
        {/* Protected routes - all wrapped in RequireAuth and AuthenticatedLayout */}
        <Route element={<RequireAuth />}>
          <Route element={<AuthenticatedLayout />}>
            <Route path="/home" element={<Home />} />
            
            {/* Imóveis */}
            <Route path="/imoveis" element={<Imoveis />} />
            <Route path="/imoveis/meus" element={<MeusImoveis />} />
            <Route path="/imoveis/novo" element={<NovoImovel />} />
            <Route path="/imovel/:id" element={<Imovel />} />
            
            {/* Condominios */}
            <Route path="/condominios" element={<Condominios />} />
            <Route path="/condominios/meus" element={<MeusCondominios />} />
            <Route path="/condominios/novo" element={<NovoCondominio />} />
            <Route path="/condominio/:id" element={<Condominio />} />
            
            {/* Permutas */}
            <Route path="/permutas" element={<Permutas />} />
            <Route path="/permutas/minhas" element={<MinhasPermutas />} />
            <Route path="/permutas/nova" element={<NovaPermuta />} />
            <Route path="/permuta/imovel/:id" element={<PermutaImovel />} />
            <Route path="/permuta/automovel/:id" element={<PermutaAutomovel />} />
            
            {/* Clientes */}
            <Route path="/clientes" element={<Clientes />} />
            <Route path="/clientes/meus" element={<MeusClientes />} />
            <Route path="/clientes/novo" element={<NovoCliente />} />
            <Route path="/cliente/:id" element={<Cliente />} />
            
            {/* Corretores */}
            <Route path="/corretores" element={<Corretores />} />
            <Route path="/corretor/:id" element={<Corretor />} />
            
            {/* Matches */}
            <Route path="/matches" element={<Matches />} />
            <Route path="/matches/:matchId" element={<MatchDossie />} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  )
}

export default Rotas
