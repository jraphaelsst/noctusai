import { Route, Routes } from 'react-router-dom'

import PrivateRoute from './utils/PrivateRoute'
import AuthenticatedRedirect from './utils/AuthenticatedRedirect'
import Login from './pages/Login'
import Cadastro from './pages/Cadastro'
import Landing from './pages/Landing'
import Home from './pages/Home'

import Imoveis from './pages/Imoveis'
import NovoImovel from './pages/Imoveis/Novo'
import MeusImoveis from './pages/Imoveis/Meus'
import Imovel from './pages/Imoveis/Imovel'

import Permutas from './pages/Permutas'
import MinhasPermutas from './pages/Permutas/Minhas'
import NovaPermuta from './pages/Permutas/Nova'

import Clientes from './pages/Clientes'
import MeusClientes from './pages/Clientes/Meus'
import NovoCliente from './pages/Clientes/Novo'

import NovoCondominio from './pages/Condominios/Novo'
import MeusCondominios from './pages/Condominios/Meus'
import Condominios from './pages/Condominios'

const Rotas = () => {
  return (
    <>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route
          path="/login"
          element={
            <AuthenticatedRedirect>
              <Login />
            </AuthenticatedRedirect>
          }
        />
        <Route
          path="/cadastro"
          element={
            <AuthenticatedRedirect>
              <Cadastro />
            </AuthenticatedRedirect>
          }
        />
        <Route
          path="/home"
          element={
            <PrivateRoute>
              <Home />
            </PrivateRoute>
          }
        />
        <Route
          path="/imoveis"
          element={
            <PrivateRoute>
              <Imoveis />
            </PrivateRoute>
          }
        />
        <Route
          path="/imoveis/meus"
          element={
            <PrivateRoute>
              <MeusImoveis />
            </PrivateRoute>
          }
        />
        <Route
          path="/imoveis/novo"
          element={
            <PrivateRoute>
              <NovoImovel />
            </PrivateRoute>
          }
        />
        <Route
          path="imovel/:id"
          element={
            <PrivateRoute>
              <Imovel />
            </PrivateRoute>
          }
        />
        <Route
          path="/condominios"
          element={
            <PrivateRoute>
              <Condominios />
            </PrivateRoute>
          }
        />
        <Route
          path="/condominios/meus"
          element={
            <PrivateRoute>
              <MeusCondominios />
            </PrivateRoute>
          }
        />
        <Route
          path="/condominios/novo"
          element={
            <PrivateRoute>
              <NovoCondominio />
            </PrivateRoute>
          }
        />
        <Route
          path="condominio/:id"
          element={
            <PrivateRoute>
              <Imovel />
            </PrivateRoute>
          }
        />
        <Route
          path="/permutas"
          element={
            <PrivateRoute>
              <Permutas />
            </PrivateRoute>
          }
        />
        <Route
          path="/permutas/minhas"
          element={
            <PrivateRoute>
              <MinhasPermutas />
            </PrivateRoute>
          }
        />
        <Route
          path="/permutas/nova"
          element={
            <PrivateRoute>
              <NovaPermuta />
            </PrivateRoute>
          }
        />
        <Route
          path="/clientes"
          element={
            <PrivateRoute>
              <Clientes />
            </PrivateRoute>
          }
        />
        <Route
          path="/clientes/meus"
          element={
            <PrivateRoute>
              <MeusClientes />
            </PrivateRoute>
          }
        />
        <Route
          path="/clientes/novo"
          element={
            <PrivateRoute>
              <NovoCliente />
            </PrivateRoute>
          }
        />
      </Routes>
    </>
  )
}

export default Rotas
