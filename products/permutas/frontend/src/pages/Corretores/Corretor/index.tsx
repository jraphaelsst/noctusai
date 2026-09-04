import { useParams, useNavigate } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import swal from 'sweetalert2'

import {
  Container,
  Banner,
  Avatar,
  Infos,
  Nome,
  InfoItem,
  Sections,
  TituloSecao,
  Card,
  ActionButtons,
  ActionButton,
  MatchesContainer,
  MatchSection,
  MatchSectionTitle,
  CardGrid,
  MatchCard,
  MatchBadge,
  MatchCardTitle,
  MatchCardDetail,
  MatchCardValue,
  EmptyMessage
} from './styles'

import useAxios from '../../../utils/useAxios'
import { LoadingScreen } from '../../../components/Spinner'
import { EditIcon, DeleteIcon } from '../../../components/Icons'
import Modal from '../../../components/Modal'
import CorretorEditForm from '../../../components/ModalForms/CorretorEditForm'

type CorretorType = {
  id: number
  nome: string
  telefone: string
  email: string
  creci: string
}

type ImovelType = {
  id: number
  ref: string
  tipo_nome: string | null
  zona_nome: string | null
  valor_venda: number
  condominio_nome: string | null
  condominio_bairro: string | null
  proprietario_nome: string | null
  corretor: number | null
}

type PermutaImovelType = {
  id: number
  codigo: string
  tipo_nome: string | null
  zona_nome: string | null
  estado: string
  bairro: string
  valor: number
  proprietario_nome: string
  corretor: number | null
}

type PermutaAutomovelType = {
  id: number
  codigo: string
  tipo_nome: string | null
  marca: string
  modelo: string
  motor: string
  valor: number
  proprietario_nome: string
  corretor: number | null
}

import { formatCurrency } from '../../../utils/formatCurrency'

const Corretor = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const api = useAxios()

  const [corretor, setCorretor] = useState<CorretorType | null>(null)
  const [imoveis, setImoveis] = useState<ImovelType[]>([])
  const [permutasImoveis, setPermutasImoveis] = useState<PermutaImovelType[]>([])
  const [permutasAutomoveis, setPermutasAutomoveis] = useState<PermutaAutomovelType[]>([])
  const [loading, setLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)

  const fetchData = async () => {
    setLoading(true)
    try {
      const [corretorRes, imoveisRes, permutasImovelRes, permutasAutomovelRes] = await Promise.all([
        api.get(`/corretor/${id}/`),
        api.get('/imovel/'),
        api.get('/permuta/imovel/'),
        api.get('/permuta/automovel/')
      ])
      setCorretor(corretorRes.data)
      setImoveis(imoveisRes.data)
      setPermutasImoveis(permutasImovelRes.data)
      setPermutasAutomoveis(permutasAutomovelRes.data)
    } catch (error) {
      console.error('Error fetching corretor:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (id) {
      fetchData()
    }
  }, [id])

  const imoveisDoCorretor = useMemo(() => {
    if (!corretor) return []
    return imoveis.filter(imovel => imovel.corretor === corretor.id)
  }, [imoveis, corretor])

  const permutasImoveisDoCorretor = useMemo(() => {
    if (!corretor) return []
    return permutasImoveis.filter(permuta => permuta.corretor === corretor.id)
  }, [permutasImoveis, corretor])

  const permutasAutomoveisDoCorretor = useMemo(() => {
    if (!corretor) return []
    return permutasAutomoveis.filter(permuta => permuta.corretor === corretor.id)
  }, [permutasAutomoveis, corretor])

  const handleEdit = () => {
    setIsModalOpen(true)
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
  }

  const handleDelete = async () => {
    const result = await swal.fire({
      title: 'Confirmar exclusão',
      text: 'Tem certeza que deseja excluir este corretor? Esta ação não pode ser desfeita.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#6b7280',
      confirmButtonText: 'Sim, excluir',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed) {
      try {
        await api.delete(`/corretor/${id}/`)
        swal.fire('Excluído!', 'O corretor foi excluído com sucesso.', 'success')
        navigate('/corretores')
      } catch (error) {
        swal.fire('Erro', 'Não foi possível excluir o corretor.', 'error')
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

  if (!corretor) {
    return (
      <Container>
        <Banner>
          <p style={{ color: 'white' }}>Corretor não encontrado</p>
        </Banner>
      </Container>
    )
  }

  const getInitials = (name: string) => {
    return name.split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase()
  }

  return (
    <Container>
      <Banner>
        <Avatar>{getInitials(corretor.nome)}</Avatar>
        <Infos>
          <Nome>{corretor.nome}</Nome>
          <InfoItem>
            <strong>CRECI:</strong> {corretor.creci || '-'}
          </InfoItem>
          <InfoItem>
            <strong>Telefone:</strong> {corretor.telefone || '-'}
          </InfoItem>
          <InfoItem>
            <strong>Email:</strong> {corretor.email || '-'}
          </InfoItem>
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

      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title="Editar Corretor"
      >
        <CorretorEditForm
          onSuccess={() => {
            fetchData()
            handleCloseModal()
          }}
          onClose={handleCloseModal}
          initialData={corretor}
        />
      </Modal>

      <Sections>
        <TituloSecao>Informações do Corretor</TituloSecao>
        <Card>
          <InfoItem>
            <strong>ID:</strong> {corretor.id}
          </InfoItem>
          <InfoItem>
            <strong>Nome Completo:</strong> {corretor.nome}
          </InfoItem>
          <InfoItem>
            <strong>CRECI:</strong> {corretor.creci || '-'}
          </InfoItem>
          <InfoItem>
            <strong>Telefone:</strong> {corretor.telefone || '-'}
          </InfoItem>
          <InfoItem>
            <strong>Email:</strong> {corretor.email || '-'}
          </InfoItem>
        </Card>

        <TituloSecao>Imóveis do Corretor ({imoveisDoCorretor.length})</TituloSecao>
        <MatchesContainer>
          {imoveisDoCorretor.length > 0 ? (
            <CardGrid>
              {imoveisDoCorretor.map(imovel => (
                <MatchCard key={imovel.id} onClick={() => navigate(`/imovel/${imovel.id}`)}>
                  <MatchBadge>Imóvel</MatchBadge>
                  <MatchCardTitle>{imovel.ref}</MatchCardTitle>
                  <MatchCardDetail>{imovel.tipo_nome || '-'}</MatchCardDetail>
                  <MatchCardDetail>{imovel.condominio_nome}</MatchCardDetail>
                  <MatchCardDetail>{imovel.condominio_bairro}</MatchCardDetail>
                  <MatchCardDetail>Proprietário: {imovel.proprietario_nome || '-'}</MatchCardDetail>
                  <MatchCardValue>{formatCurrency(imovel.valor_venda)}</MatchCardValue>
                </MatchCard>
              ))}
            </CardGrid>
          ) : (
            <EmptyMessage>Nenhum imóvel cadastrado para este corretor</EmptyMessage>
          )}
        </MatchesContainer>

        <TituloSecao>Permutas de Imóveis ({permutasImoveisDoCorretor.length})</TituloSecao>
        <MatchesContainer>
          {permutasImoveisDoCorretor.length > 0 ? (
            <CardGrid>
              {permutasImoveisDoCorretor.map(permuta => (
                <MatchCard key={permuta.id} onClick={() => navigate(`/permuta/imovel/${permuta.id}`)}>
                  <MatchBadge>Permuta Imóvel</MatchBadge>
                  <MatchCardTitle>{permuta.codigo}</MatchCardTitle>
                  <MatchCardDetail>{permuta.tipo_nome || '-'}</MatchCardDetail>
                  <MatchCardDetail>{permuta.bairro}, {permuta.estado}</MatchCardDetail>
                  <MatchCardDetail>Proprietário: {permuta.proprietario_nome}</MatchCardDetail>
                  <MatchCardValue>{formatCurrency(permuta.valor)}</MatchCardValue>
                </MatchCard>
              ))}
            </CardGrid>
          ) : (
            <EmptyMessage>Nenhuma permuta de imóvel cadastrada para este corretor</EmptyMessage>
          )}
        </MatchesContainer>

        <TituloSecao>Permutas de Automóveis ({permutasAutomoveisDoCorretor.length})</TituloSecao>
        <MatchesContainer>
          {permutasAutomoveisDoCorretor.length > 0 ? (
            <CardGrid>
              {permutasAutomoveisDoCorretor.map(permuta => (
                <MatchCard key={permuta.id} onClick={() => navigate(`/permuta/automovel/${permuta.id}`)}>
                  <MatchBadge>Permuta Automóvel</MatchBadge>
                  <MatchCardTitle>{permuta.codigo}</MatchCardTitle>
                  <MatchCardDetail>{permuta.tipo_nome || '-'}</MatchCardDetail>
                  <MatchCardDetail>{permuta.marca} {permuta.modelo} {permuta.motor}</MatchCardDetail>
                  <MatchCardDetail>Proprietário: {permuta.proprietario_nome}</MatchCardDetail>
                  <MatchCardValue>{formatCurrency(permuta.valor)}</MatchCardValue>
                </MatchCard>
              ))}
            </CardGrid>
          ) : (
            <EmptyMessage>Nenhuma permuta de automóvel cadastrada para este corretor</EmptyMessage>
          )}
        </MatchesContainer>
      </Sections>
    </Container>
  )
}

export default Corretor
