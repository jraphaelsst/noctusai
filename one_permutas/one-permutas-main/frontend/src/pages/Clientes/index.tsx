import Container from '../../containers/Container'

import Button from '../../components/Button'
import { LinkTo } from '../Imoveis/Meus/styles'
import { CardsContainer } from '../Imoveis/styles'
import CardCliente from '../../components/CardCliente'

import { useGetClientesQuery } from '../../services/api'

export type ClienteType = {
  id: number
  criado_por: string
  corretor: string
  nome: string
  telefone: string
  email: string
}

const Clientes = () => {
  const { data: clientes } = useGetClientesQuery()

  return (
    <Container title="Clientes">
      <Button type="button">
        <LinkTo to="/clientes/novo">Cadastrar Novo</LinkTo>
      </Button>
      <CardsContainer>
        {clientes?.map((cliente) => (
          <LinkTo to={`/cliente/${cliente.id}`} key={cliente.id}>
            <CardCliente
              corretor={cliente.corretor}
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

export default Clientes
