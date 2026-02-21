import Container from '../../containers/Container'

import { TableTitle } from '../Imoveis/Novo/styles'

import {
  useGetPermutasImovelQuery,
  useGetPermutasAutomovelQuery
} from '../../services/api'
import { CardsContainer } from '../Imoveis/styles'
import CardPermuta from '../../components/CardPermuta'
import { LinkTo } from '../Imoveis/Meus/styles'
import Button from '../../components/Button'
import {
  getMotor,
  getTipoAutomovel,
  getTipoImovel,
  getZona
} from '../../components/CardPermuta/utils'

export type PermutaImovelType = {
  id: string
  criado_por: string
  criado_por_nome: string
  corretor: string
  tipo: string
  condominio: string
  zona: string
  cep: string
  estado: string
  cidade: string
  bairro: string
  endereco: string
  numero: number
  valor: number
  proprietario_nome: string
}

export type PermutaAutomovelType = {
  id: number
  criado_por: string
  criado_por_nome: string
  corretor: string
  tipo: string
  marca: string
  modelo: string
  motor: string
  valor: number
  proprietario_nome: string
}

const Permutas = () => {
  const { data: permutasImovel } = useGetPermutasImovelQuery()
  const { data: permutasAutomovel } = useGetPermutasAutomovelQuery()

  return (
    <Container title="Permutas">
      <>
        <Button type="button">
          <LinkTo to="/permutas/nova">Cadastrar nova</LinkTo>
        </Button>
        <TableTitle style={{ textAlign: 'center' }}>Imóveis</TableTitle>
        <CardsContainer>
          {permutasImovel ? (
            permutasImovel?.map((permutaImovel) => (
              <LinkTo
                to={`/permutas/imovel/${permutaImovel.id}`}
                key={permutaImovel.id}
              >
                <CardPermuta
                  tipoPermuta="imovel"
                  tipo={getTipoImovel(permutaImovel.tipo)}
                  corretor={permutaImovel.corretor}
                  cidade={permutaImovel.cidade}
                  bairro={permutaImovel.bairro}
                  zona={getZona(permutaImovel.zona)}
                  condominio={permutaImovel.condominio}
                  valor={permutaImovel.valor}
                />
              </LinkTo>
            ))
          ) : (
            <div>Sem permutas imóveis disponíveis</div>
          )}
        </CardsContainer>
        <TableTitle style={{ textAlign: 'center' }}>Automóveis</TableTitle>
        <CardsContainer>
          {permutasAutomovel ? (
            permutasAutomovel?.map((permutaAutomovel) => (
              <LinkTo
                to={`permutas/automovel/${permutaAutomovel.id}`}
                key={permutaAutomovel.id}
              >
                <CardPermuta
                  tipoPermuta="automovel"
                  tipo={getTipoAutomovel(permutaAutomovel.tipo)}
                  corretor={permutaAutomovel.corretor}
                  marca={permutaAutomovel.marca}
                  modelo={permutaAutomovel.modelo}
                  motor={getMotor(permutaAutomovel.motor)}
                  valor={permutaAutomovel.valor}
                />
              </LinkTo>
            ))
          ) : (
            <div>Sem permutas automóveis cadastradas</div>
          )}
        </CardsContainer>
      </>
    </Container>
  )
}

export default Permutas
