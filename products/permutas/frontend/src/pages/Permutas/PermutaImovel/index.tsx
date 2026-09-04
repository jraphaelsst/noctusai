import { useParams, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import swal from 'sweetalert2'

import {
  Container,
  Banner,
  Icon,
  Infos,
  Tipo,
  InfoItem,
  Valor,
  Sections,
  TituloSecao,
  Card,
  CardGrid,
  ActionButtons,
  ActionButton,
  MatchesContainer,
  MatchSection,
  MatchSectionTitle,
  MatchCard,
  MatchBadge,
  MatchCardTitle,
  MatchCardDetail,
  MatchCardValue,
  EmptyMessage,
  InteresseSection,
  InteresseSectionHeader,
  AddButton,
  InteresseTable,
  InteresseTableHeader,
  InteresseTableBody,
  TableActions,
  TableActionButton
} from './styles'

import useAxios from '../../../utils/useAxios'
import { LoadingScreen } from '../../../components/Spinner'
import { EditIcon, DeleteIcon } from '../../../components/Icons'
import Modal from '../../../components/Modal'
import PermutaImovelEditForm from '../../../components/ModalForms/PermutaImovelEditForm'
import InteressePermutaImovelForm, { InteressePermutaImovelData } from '../../../components/ModalForms/InteressePermutaImovelForm'

type ImovelInteressadoType = {
  id: number
  ref: string
  tipo_nome: string | null
  zona_nome: string | null
  valor_venda: number
  condominio_nome: string | null
  condominio_bairro: string | null
  proprietario_nome: string | null
}

type InteressePermutaType = {
  id: number
  tipo_imovel: number | null
  tipo_imovel_nome: string | null
  zona: number | null
  zona_nome: string | null
  estado: string | null
  valor_minimo: number | null
  valor_maximo: number | null
  observacoes: string
}

type PermutaImovelType = {
  id: number
  ref: string | null
  proprietario: number
  proprietario_nome: string
  criado_por: number
  criado_por_nome: string
  corretor: number | null
  corretor_nome: string | null
  tipo: number | null
  tipo_nome: string | null
  condominio: number | null
  zona: number | null
  zona_nome: string | null
  cep: string
  estado: string
  cidade: string
  bairro: string
  endereco: string
  numero: string
  valor: number
  imoveis_interessados: ImovelInteressadoType[]
}

const PermutaImovel = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const api = useAxios()

  const [permuta, setPermuta] = useState<PermutaImovelType | null>(null)
  const [loading, setLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isInteresseModalOpen, setIsInteresseModalOpen] = useState(false)
  const [interesses, setInteresses] = useState<InteressePermutaType[]>([])

  const fetchInteresses = async () => {
    try {
      const res = await api.get(`/permuta/interesse-imovel/?permuta_imovel=${id}`)
      setInteresses(res.data.results || res.data || [])
    } catch (error) {
      console.error('Error fetching interesses:', error)
    }
  }

  const fetchData = async () => {
    setLoading(true)
    try {
      const permutaRes = await api.get(`/permuta/imovel/${id}/`)
      setPermuta(permutaRes.data)
      await fetchInteresses()
    } catch (error) {
      console.error('Error fetching permuta:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (id) {
      fetchData()
    }
  }, [id])

  const handleCloseModal = () => {
    setIsModalOpen(false)
  }

  const handleCloseInteresseModal = () => {
    setIsInteresseModalOpen(false)
  }

  const handleAddInteresse = async (data: InteressePermutaImovelData) => {
    try {
      await api.post('/permuta/interesse-imovel/', {
        permuta_imovel: id,
        tipo_imovel: data.tipo_imovel || null,
        zona: data.zona || null,
        cep: data.cep,
        estado: data.estado,
        cidade: data.cidade,
        bairro: data.bairro,
        endereco: data.endereco,
        valor_minimo: data.valor_minimo ? parseInt(data.valor_minimo) : null,
        valor_maximo: data.valor_maximo ? parseInt(data.valor_maximo) : null,
        observacoes: data.observacoes
      })
      swal.fire('Sucesso', 'Interesse adicionado com sucesso!', 'success')
      fetchInteresses()
    } catch (error) {
      swal.fire('Erro', 'Não foi possível adicionar o interesse.', 'error')
    }
  }

  const handleDeleteInteresse = async (interesseId: number) => {
    const result = await swal.fire({
      title: 'Confirmar exclusão',
      text: 'Tem certeza que deseja excluir este interesse?',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#6b7280',
      confirmButtonText: 'Sim, excluir',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed) {
      try {
        await api.delete(`/permuta/interesse-imovel/${interesseId}/`)
        swal.fire('Excluído!', 'Interesse excluído com sucesso.', 'success')
        fetchInteresses()
      } catch (error) {
        swal.fire('Erro', 'Não foi possível excluir o interesse.', 'error')
      }
    }
  }

  const formatCurrency = (value: number | null) => {
    if (value === null) return '-'
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value)
  }

  const imoveisInteressados = permuta?.imoveis_interessados || []

  const handleEdit = () => {
    setIsModalOpen(true)
  }

  const handleDelete = async () => {
    const result = await swal.fire({
      title: 'Confirmar exclusão',
      text: 'Tem certeza que deseja excluir esta permuta? Esta ação não pode ser desfeita.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#6b7280',
      confirmButtonText: 'Sim, excluir',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed) {
      try {
        await api.delete(`/permuta/imovel/${id}/`)
        swal.fire('Excluído!', 'A permuta foi excluída com sucesso.', 'success')
        navigate('/permutas')
      } catch (error) {
        swal.fire('Erro', 'Não foi possível excluir a permuta.', 'error')
      }
    }
  }

  if (loading) {
    return (
      <Container>
        <LoadingScreen />
      </Container>
    )
  }

  if (!permuta) {
    return (
      <Container>
        <Banner>
          <p style={{ color: 'white' }}>Permuta não encontrada</p>
        </Banner>
      </Container>
    )
  }

  return (
    <Container>
      <Banner>
        <Icon>🏠</Icon>
        <Infos>
          <Tipo>{permuta.tipo_nome || '-'}</Tipo>
          <InfoItem>
            <strong>Proprietário:</strong> {permuta.proprietario_nome}
          </InfoItem>
          <InfoItem>
            <strong>Localização:</strong> {permuta.cidade} - {permuta.estado}
          </InfoItem>
          <InfoItem>
            <strong>Zona:</strong> {permuta.zona_nome || '-'}
          </InfoItem>
          <Valor>{formatCurrency(permuta.valor)}</Valor>
          <ActionButtons>
            <ActionButton onClick={handleEdit} title="Editar">
              <EditIcon size={18} />
            </ActionButton>
            <ActionButton $variant="delete" onClick={handleDelete} title="Excluir">
              <DeleteIcon size={18} />
            </ActionButton>
          </ActionButtons>
        </Infos>
      </Banner>

      {permuta && (
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title="Editar Permuta de Imóvel"
        >
          <PermutaImovelEditForm
            onSuccess={() => {
              fetchData()
              handleCloseModal()
            }}
            onClose={handleCloseModal}
            initialData={permuta}
          />
        </Modal>
      )}

      <Sections>
        <CardGrid>
          <div>
            <TituloSecao>Informações do Imóvel</TituloSecao>
            <Card>
              <InfoItem>
                <strong>ID:</strong> {permuta.id}
              </InfoItem>
              <InfoItem>
                <strong>Tipo:</strong> {permuta.tipo_nome || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Valor:</strong> {formatCurrency(permuta.valor)}
              </InfoItem>
              <InfoItem>
                <strong>CEP:</strong> {permuta.cep || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Endereço:</strong> {permuta.endereco || '-'}, {permuta.numero || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Bairro:</strong> {permuta.bairro || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Cidade:</strong> {permuta.cidade || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Estado:</strong> {permuta.estado || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Zona:</strong> {permuta.zona_nome || '-'}
              </InfoItem>
            </Card>
          </div>

          <div>
            <TituloSecao>Informações do Proprietário</TituloSecao>
            <Card>
              <InfoItem>
                <strong>Nome:</strong> {permuta.proprietario_nome}
              </InfoItem>
              <InfoItem>
                <strong>Corretor:</strong> {permuta.corretor_nome || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Criado por:</strong> {permuta.criado_por_nome || '-'}
              </InfoItem>
            </Card>
          </div>
        </CardGrid>

        <InteresseSection>
          <InteresseSectionHeader>
            <TituloSecao style={{ marginBottom: 0 }}>O que o Proprietário Aceita em Troca</TituloSecao>
            <AddButton onClick={() => setIsInteresseModalOpen(true)}>
              + Adicionar Interesse
            </AddButton>
          </InteresseSectionHeader>
          
          {interesses.length > 0 ? (
            <InteresseTable>
              <InteresseTableHeader>
                <tr>
                  <th>Tipo de Imóvel</th>
                  <th>Zona</th>
                  <th>Estado</th>
                  <th>Valor Mínimo</th>
                  <th>Valor Máximo</th>
                  <th>Ações</th>
                </tr>
              </InteresseTableHeader>
              <InteresseTableBody>
                {interesses.map((interesse) => (
                  <tr key={interesse.id}>
                    <td>{interesse.tipo_imovel_nome || 'Qualquer'}</td>
                    <td>{interesse.zona_nome || 'Qualquer'}</td>
                    <td>{interesse.estado || 'Qualquer'}</td>
                    <td>{formatCurrency(interesse.valor_minimo)}</td>
                    <td>{formatCurrency(interesse.valor_maximo)}</td>
                    <td>
                      <TableActions>
                        <TableActionButton 
                          $variant="delete" 
                          onClick={() => handleDeleteInteresse(interesse.id)}
                          title="Excluir"
                        >
                          <DeleteIcon size={14} />
                        </TableActionButton>
                      </TableActions>
                    </td>
                  </tr>
                ))}
              </InteresseTableBody>
            </InteresseTable>
          ) : (
            <EmptyMessage>
              Nenhum interesse cadastrado. Adicione um interesse para ativar o matching bilateral.
            </EmptyMessage>
          )}
        </InteresseSection>

        <Modal
          isOpen={isInteresseModalOpen}
          onClose={handleCloseInteresseModal}
          title="Adicionar Interesse de Permuta"
        >
          <InteressePermutaImovelForm
            onAdd={handleAddInteresse}
            onClose={handleCloseInteresseModal}
          />
        </Modal>

        <TituloSecao>Imóveis Interessados</TituloSecao>
        <MatchesContainer>
          <MatchSection>
            <MatchSectionTitle>
              Imóveis que buscam esta permuta ({imoveisInteressados.length})
            </MatchSectionTitle>
            {imoveisInteressados.length > 0 ? (
              imoveisInteressados.map((imovel) => (
                <MatchCard 
                  key={imovel.id}
                  onClick={() => navigate(`/imovel/${imovel.id}`)}
                >
                  <MatchBadge>Match</MatchBadge>
                  <MatchCardTitle>{imovel.ref}</MatchCardTitle>
                  <MatchCardDetail>{imovel.tipo_nome || '-'}{imovel.zona_nome ? ` - ${imovel.zona_nome}` : ''}</MatchCardDetail>
                  <MatchCardDetail>{imovel.condominio_nome || '-'}</MatchCardDetail>
                  <MatchCardDetail>{imovel.condominio_bairro || '-'}</MatchCardDetail>
                  <MatchCardDetail>
                    Proprietário: {imovel.proprietario_nome || '-'}
                  </MatchCardDetail>
                  <MatchCardValue>{formatCurrency(imovel.valor_venda)}</MatchCardValue>
                </MatchCard>
              ))
            ) : (
              <EmptyMessage>
                Nenhum imóvel interessado encontrado
              </EmptyMessage>
            )}
          </MatchSection>
        </MatchesContainer>
      </Sections>
    </Container>
  )
}

export default PermutaImovel
