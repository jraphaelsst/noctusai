import Container from '../../../containers/Container'

import { jwtDecode } from 'jwt-decode'

import { useGetClientesQuery } from '../../../services/api'
import CardCliente from '../../../components/CardCliente'
import { LinkTo } from '../../Imoveis/Meus/styles'
import { CardsContainer } from '../../Imoveis/styles'
import Button from '../../../components/Button'

export type ClienteType = {
  id: number
  criado_por: string
  corretor: number | null
  corretor_nome: string | null
  nome: string
  telefone: string
  email: string
}

const MeusClientes = () => {
  const token = localStorage.getItem('authTokens')
  const decoded = jwtDecode(token!)
  const user_id = decoded.user_id

  const { data: clientes } = useGetClientesQuery()
  const clientes_filtrados = clientes?.filter(
    (cliente) => cliente.criado_por === user_id
  )

  return (
    <Container title=" Meus Clientes">
      <Button type="button">
        <LinkTo to="/clientes/novo">Cadastrar Novo</LinkTo>
      </Button>
      <CardsContainer>
        {clientes_filtrados?.map((cliente) => (
          <LinkTo to={`/cliente/${cliente.id}`} key={cliente.id}>
            <CardCliente
              corretor={cliente.corretor_nome || '-'}
              nome={cliente.nome}
              telefone={cliente.telefone}
              email={cliente.email}
            />
          </LinkTo>
        ))}
      </CardsContainer>
    </Container>
  )
}

export default MeusClientes
