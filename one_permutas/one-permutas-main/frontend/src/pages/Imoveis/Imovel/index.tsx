import { useParams } from 'react-router-dom'

import {
  Bairro,
  Banner,
  Condominio,
  Container,
  Corretor,
  CorretorTipo,
  DescritivoContainer,
  Email,
  Endereco,
  Icons,
  Image,
  Infos,
  Interesses,
  Km,
  Nome,
  Permutas,
  Proprietario,
  ProprietarioTitle,
  Ref,
  Sections,
  Telefone,
  TituloSecao,
  Tipo,
  Valor
} from './styles'

import {
  useGetImovelQuery,
  useGetPermutasAutomovelQuery,
  useGetPermutasImovelQuery
} from '../../../services/api'
import { Interesse } from '../../../store/reducers/overlayInteresses'
import {
  Table,
  TableHead,
  TableCell,
  TableRow,
  TableTitle
} from '../Novo/styles'
import { PermutaAutomovelType, PermutaImovelType } from '../../Permutas'

const Imovel = () => {
  const { id } = useParams()
  const { data: imovel } = useGetImovelQuery(id!)
  const { data: permutasImoveis } = useGetPermutasImovelQuery()
  const { data: permutasAutomoveis } = useGetPermutasAutomovelQuery()

  if (!imovel) {
    return <h3>Carregando...</h3>
  }

  const interessesImoveis = JSON.parse(imovel.interesses_imoveis)
  const interessesAutomoveis = JSON.parse(imovel.interesses_automoveis)

  const permutasImoveis_filtradas: PermutaImovelType[] = []
  interessesImoveis.map((interesseImovel: Interesse) => {
    permutasImoveis?.map((permutaImovel) => {
      if (
        interesseImovel.valor_minimo <= permutaImovel.valor &&
        interesseImovel.valor_maximo >= permutaImovel.valor &&
        interesseImovel.tipo_imovel == permutaImovel.tipo &&
        interesseImovel.estado == permutaImovel.estado &&
        interesseImovel.zona == permutaImovel.zona
      ) {
        permutasImoveis_filtradas.push(permutaImovel)
      }
    })
  })

  const permutasAutomoveis_filtradas: PermutaAutomovelType[] = []
  interessesAutomoveis.map((interesseAutomovel: Interesse) => {
    permutasAutomoveis?.map((permutaAutomovel) => {
      if (
        interesseAutomovel.tipo_automovel == permutaAutomovel.tipo &&
        interesseAutomovel.valor_minimo <= permutaAutomovel.valor &&
        interesseAutomovel.valor_maximo >= permutaAutomovel.valor
      ) {
        permutasAutomoveis_filtradas.push(permutaAutomovel)
      }
    })
  })

  return (
    <Container>
      <Banner>
        <Image />
        <Infos>
          <DescritivoContainer>
            <div>
              <Ref>{imovel.ref}</Ref>
              <Valor>R$ {imovel.valor_venda},00</Valor>
              <CorretorTipo>
                <Corretor>{imovel.corretor}</Corretor>
                <Tipo>{imovel.tipo}</Tipo>
              </CorretorTipo>
            </div>
            <div>
              <Condominio>{imovel.condominio_nome}</Condominio>
              <Bairro>{imovel.condominio_bairro}</Bairro>
              <Km>Km {imovel.condominio_km}</Km>
              <Endereco>{imovel.condominio_endereco}</Endereco>
            </div>
          </DescritivoContainer>
          <Proprietario>
            <ProprietarioTitle>Proprietário</ProprietarioTitle>
            <Nome>{imovel.proprietario_nome}</Nome>
            <Telefone>{imovel.proprietario_telefone}</Telefone>
            <Email>{imovel.proprietario_email}</Email>
          </Proprietario>
          <Icons>
            <i className="fa-regular fa-pen-to-square" />
            <i className="fa-solid fa-xmark" />
          </Icons>
        </Infos>
      </Banner>
      <Sections>
        <Interesses>
          <TituloSecao style={{ textAlign: 'center' }}>Interesses</TituloSecao>
          <TableTitle style={{ textAlign: 'center' }}>Imóveis</TableTitle>
          <Table>
            <thead>
              <TableRow>
                <TableHead>Tipo</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Zona</TableHead>
                <TableHead>Valor Máximo</TableHead>
                <TableHead>Valor Mínimo</TableHead>
              </TableRow>
            </thead>
            <tbody>
              {interessesImoveis.map((item: Interesse, index: number) => (
                <TableRow key={index}>
                  <TableCell>{item.tipo_imovel}</TableCell>
                  <TableCell>{item.estado}</TableCell>
                  <TableCell>{item.zona}</TableCell>
                  <TableCell>{item.valor_maximo}</TableCell>
                  <TableCell>{item.valor_minimo}</TableCell>
                </TableRow>
              ))}
            </tbody>
          </Table>
          <TableTitle style={{ textAlign: 'center' }}>Automóveis</TableTitle>
          <Table>
            <thead>
              <TableRow>
                <TableHead>Tipo</TableHead>
                <TableHead>Valor Máximo</TableHead>
                <TableHead>Valor Mínimo</TableHead>
              </TableRow>
            </thead>
            <tbody>
              {interessesAutomoveis.map((item: Interesse, index: number) => (
                <TableRow key={index}>
                  <TableCell>{item.tipo_automovel}</TableCell>
                  <TableCell>{item.valor_maximo}</TableCell>
                  <TableCell>{item.valor_minimo}</TableCell>
                </TableRow>
              ))}
            </tbody>
          </Table>
        </Interesses>
        <Permutas>
          <div>
            {permutasImoveis_filtradas.map(
              (permutaImovel: PermutaImovelType, index: number) => (
                <div key={index}>
                  <div>{permutaImovel.tipo}</div>
                  <div>{permutaImovel.estado}</div>
                  <div>{permutaImovel.zona}</div>
                  <div>{permutaImovel.bairro}</div>
                  <div>{permutaImovel.condominio}</div>
                  <div>{permutaImovel.valor}</div>
                  <div>{permutaImovel.proprietario_nome}</div>
                </div>
              )
            )}
          </div>
          <div>
            {permutasAutomoveis_filtradas.map(
              (permutaAutomovel: PermutaAutomovelType, index: number) => (
                <div key={index}>
                  <div>{permutaAutomovel.tipo}</div>
                  <div>{permutaAutomovel.marca}</div>
                  <div>{permutaAutomovel.modelo}</div>
                  <div>{permutaAutomovel.motor}</div>
                  <div>{permutaAutomovel.valor}</div>
                  <div>{permutaAutomovel.proprietario_nome}</div>
                </div>
              )
            )}
          </div>
        </Permutas>
      </Sections>
    </Container>
  )
}

export default Imovel
