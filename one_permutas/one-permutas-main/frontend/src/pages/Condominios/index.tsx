import Container from '../../containers/Container'

import { useGetCondominiosQuery } from '../../services/api'
import { CardsContainer } from '../Imoveis/styles'
import CardCondominio from '../../components/CardCondominio'
import { LinkTo } from '../Imoveis/Meus/styles'
import Button from '../../components/Button'

export type CondominioType = {
  id: number
  criado_por: string
  nome: string
  cep: string
  estado: string
  cidade: string
  bairro: string
  endereco: string
  numero: number
  km: number
  valor_condominio: number
}

const Condominios = () => {
  const { data: condominios } = useGetCondominiosQuery()

  return (
    <Container title="Condomínios">
      <Button type="button">
        <LinkTo to="/condominios/novo">Cadastrar Novo</LinkTo>
      </Button>
      <CardsContainer>
        {condominios?.map((condominio) => (
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

export default Condominios
