import Container from '../../../containers/Container'

import CardImovel from '../../../components/CardImovel'
import { LinkTo } from './styles'

import { useGetImoveisQuery } from '../../../services/api'
import { jwtDecode } from 'jwt-decode'
import { CardsContainer } from '../styles'
import Button from '../../../components/Button'

const MeusImoveis = () => {
  const token = localStorage.getItem('authTokens')
  const decoded = jwtDecode(token!)
  const user_id = decoded.user_id

  const { data: imoveis } = useGetImoveisQuery()
  const imoveis_filtrados = imoveis?.filter(
    (imovel) => imovel.criado_por === user_id
  )

  return (
    <Container title="Meus Imóveis">
      <Button type="button">
        <LinkTo to="/imoveis/novo">Cadastrar Novo</LinkTo>
      </Button>
      <CardsContainer>
        {imoveis_filtrados?.map((imovel) => (
          <LinkTo to={`/imovel/${imovel.id}`} key={imovel.id}>
            <CardImovel
              condominio={imovel.condominio_nome}
              corretor={imovel.corretor}
              referencia={imovel.ref}
              tipo={imovel.tipo}
              valor={imovel.valor_venda}
            />
          </LinkTo>
        ))}
      </CardsContainer>
    </Container>
  )
}

export default MeusImoveis
