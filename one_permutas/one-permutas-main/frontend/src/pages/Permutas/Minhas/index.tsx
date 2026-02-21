import Container from '../../../containers/Container'

import { jwtDecode } from 'jwt-decode'

import { TableTitle } from '../../Imoveis/Novo/styles'
import { LinkTo } from '../../Imoveis/Meus/styles'
import { CardsContainer } from '../../Imoveis/styles'
import Button from '../../../components/Button'
import CardPermuta from '../../../components/CardPermuta'

import {
  getMotor,
  getTipoAutomovel,
  getTipoImovel,
  getZona
} from '../../../components/CardPermuta/utils'
import {
  useGetPermutasImovelQuery,
  useGetPermutasAutomovelQuery
} from '../../../services/api'

const MinhasPermutas = () => {
  const token = localStorage.getItem('authTokens')
  const decoded = jwtDecode(token!)
  const user_id = decoded.user_id

  const { data: permutasImovel } = useGetPermutasImovelQuery()
  const { data: permutasAutomovel } = useGetPermutasAutomovelQuery()
  const permutasImovel_filtradas = permutasImovel?.filter(
    (permutaImovel) => permutaImovel.criado_por === user_id
  )
  const permutasAutomovel_filtradas = permutasAutomovel?.filter(
    (permutaAutomovel) => permutaAutomovel.criado_por === user_id
  )

  return (
    <Container title=" Minhas Permutas">
      <>
        <Button type="button">
          <LinkTo to="/permutas/nova">Cadastrar nova</LinkTo>
        </Button>
        <TableTitle style={{ textAlign: 'center' }}>Imóveis</TableTitle>
        <CardsContainer>
          {permutasImovel_filtradas ? (
            permutasImovel_filtradas?.map((permutaImovel) => (
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
        {permutasAutomovel_filtradas ? (
          permutasAutomovel_filtradas.map((permutaAutomovel) => (
            <LinkTo
              to={`/permutas/automovel/${permutaAutomovel.id}`}
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
      </>
    </Container>
  )
}

export default MinhasPermutas
