import Container from '../../containers/Container'

import { CardsContainer } from './styles'
import { LinkTo } from './Meus/styles'
import Button from '../../components/Button'
import CardImovel from '../../components/CardImovel'

import { useGetImoveisQuery } from '../../services/api'

export type ImovelType = {
  id: number
  criado_por: string
  corretor: string
  tipo: string
  proprietario_nome: string
  proprietario_telefone: string
  proprietario_email: string
  ref: string
  condominio_nome: string
  condominio_bairro: string
  condominio_km: string
  condominio_endereco: string
  valor_venda: number
  interesses_imoveis: string
  interesses_automoveis: string
}

const Imoveis = () => {
  const { data: imoveis } = useGetImoveisQuery()

  return (
    <Container title="Imóveis">
      <Button type="button">
        <LinkTo to="/imoveis/novo">Cadastrar Novo</LinkTo>
      </Button>
      <CardsContainer>
        {imoveis?.map((imovel) => (
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

export default Imoveis
