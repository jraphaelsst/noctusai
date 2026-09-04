import Container from '../../../containers/Container'

import { jwtDecode } from 'jwt-decode'

import { TableTitle } from '../../Imoveis/Novo/styles'
import { LinkTo } from '../../Imoveis/Meus/styles'
import { CardsContainer } from '../../Imoveis/styles'
import Button from '../../../components/Button'
import CardPermuta from '../../../components/CardPermuta'

import {
  useGetPermutasImovelQuery,
  useGetPermutasAutomovelQuery
} from '../../../services/api'

const MinhasPermutas = () => {
  const token = localStorage.getItem('authTokens')
  const decoded = jwtDecode(token!)
  const user_id = Number(decoded.user_id)

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
                  tipo={permutaImovel.tipo_nome || '-'}
                  corretor={permutaImovel.corretor_nome || '-'}
                  cidade={permutaImovel.cidade}
                  bairro={permutaImovel.bairro}
                  zona={permutaImovel.zona_nome || '-'}
                  condominio={permutaImovel.condominio ? String(permutaImovel.condominio) : undefined}
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
                tipo={permutaAutomovel.tipo_nome || '-'}
                corretor={permutaAutomovel.corretor_nome || '-'}
                marca={permutaAutomovel.marca}
                modelo={permutaAutomovel.modelo}
                motor={permutaAutomovel.motor || '-'}
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
