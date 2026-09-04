import Container from '../../../containers/Container'

import { CardsContainer } from '../../Imoveis/styles'
import { LinkTo } from '../../Imoveis/Meus/styles'
import CardCondominio from '../../../components/CardCondominio'
import Button from '../../../components/Button'

import { jwtDecode } from 'jwt-decode'

import { useGetCondominiosQuery } from '../../../services/api'

const MeusCondominios = () => {
  const token = localStorage.getItem('authTokens')
  const decoded = jwtDecode(token!)
  const user_id = decoded.user_id

  const { data: condominios } = useGetCondominiosQuery()
  const condominios_filtrados = condominios?.filter(
    (condominio) => condominio.criado_por === user_id
  )

  return (
    <Container title="Meus Condomínios">
      <Button type="button">
        <LinkTo to="/condominios/novo">Cadastrar Novo</LinkTo>
      </Button>
      <CardsContainer>
        {condominios_filtrados?.map((condominio) => (
          <LinkTo to={`/condominio/${condominio.id}`} key={condominio.id}>
            <CardCondominio
              nome={condominio.nome}
              bairro={condominio.bairro}
              km={`Km ${condominio.km}`}
              endereco={condominio.endereco}
              numero={condominio.numero}
              valor_condominio={condominio.valor_condominio}
            />
          </LinkTo>
        ))}
      </CardsContainer>
    </Container>
  )
}

export default MeusCondominios
