import { useParams, useNavigate } from 'react-router-dom'
import { useState, useEffect, useContext } from 'react'
import swal from 'sweetalert2'
import { formatCurrency } from '../../../utils/formatCurrency'

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
  Valor,
  MatchCard,
  MatchCardTitle,
  MatchCardDetail,
  MatchCardValue,
  MatchBadge,
  PermutaSection,
  ActionButtons,
  ActionButton
} from './styles'

import useAxios from '../../../utils/useAxios'
import AuthContext from '../../../context/AuthContext'
import {
  Table,
  TableHead,
  TableCell,
  TableRow,
  TableTitle
} from '../Novo/styles'
import { LoadingScreen } from '../../../components/Spinner'
import { EditIcon, DeleteIcon } from '../../../components/Icons'
import Modal from '../../../components/Modal'
import ImovelForm from '../../../components/ModalForms/ImovelForm'
import InteresseImovelForm, { InteresseImovelData } from '../../../components/ModalForms/InteresseImovelForm'
import InteresseAutomovelForm, { InteresseAutomovelData } from '../../../components/ModalForms/InteresseAutomovelForm'

type InteresseImovelType = {
  id: number
  tipo_imovel: number | null
  tipo_imovel_nome: string | null
  estado: string
  zona: number | null
  zona_nome: string | null
  valor_minimo: number | null
  valor_maximo: number | null
  observacoes: string
}

type InteresseAutomovelType = {
  id: number
  tipo_automovel: number | null
  tipo_automovel_nome: string | null
  valor_minimo: number | null
  valor_maximo: number | null
}

type ImovelCompativelType = {
  id: number
  ref: string
  tipo_nome: string | null
  zona_nome: string | null
  valor_venda: number
  condominio_nome: string | null
  condominio_bairro: string | null
  proprietario_nome: string | null
}

type PermutaImovelCompativelType = {
  id: number
  codigo: string
  tipo_nome: string | null
  zona_nome: string | null
  estado: string
  bairro: string
  condominio: string | null
  valor: number
  proprietario_nome: string | null
}

type PermutaAutomovelCompativelType = {
  id: number
  codigo: string
  tipo_nome: string | null
  marca: string
  modelo: string
  motor: string
  valor: number
  proprietario_nome: string | null
}

type ImovelType = {
  id: number
  ref: string
  valor_venda: number
  corretor: string
  tipo: number | null
  tipo_nome: string | null
  zona: number | null
  zona_nome: string | null
  condominio_nome: string
  condominio_bairro: string
  condominio_km: string
  condominio_endereco: string
  proprietario_nome: string
  proprietario_telefone: string
  proprietario_email: string
  interesses_imoveis_lista: InteresseImovelType[]
  interesses_automoveis_lista: InteresseAutomovelType[]
  imoveis_compativeis: ImovelCompativelType[]
  imoveis_interessados: ImovelCompativelType[]
  permutas_imoveis_compativeis: PermutaImovelCompativelType[]
  permutas_automoveis_compativeis: PermutaAutomovelCompativelType[]
}

const Imovel = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const api = useAxios()
  const { user } = useContext(AuthContext)

  const [imovel, setImovel] = useState<ImovelType | null>(null)
  const [loading, setLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isInteresseImovelModalOpen, setIsInteresseImovelModalOpen] = useState(false)
  const [isInteresseAutomovelModalOpen, setIsInteresseAutomovelModalOpen] = useState(false)
  const [editingInteresseImovel, setEditingInteresseImovel] = useState<InteresseImovelType | null>(null)
  const [editingInteresseAutomovel, setEditingInteresseAutomovel] = useState<InteresseAutomovelType | null>(null)

  const fetchData = async () => {
    if (!user) return

    setLoading(true)
    try {
      const imovelRes = await api.get(`/imovel/${id}/`)
      setImovel(imovelRes.data)
    } catch (error) {
      console.error('Error fetching data:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [id, user])

  const handleCloseModal = () => {
    setIsModalOpen(false)
  }

  const interessesImoveis = imovel?.interesses_imoveis_lista || []
  const interessesAutomoveis = imovel?.interesses_automoveis_lista || []
  const permutasImoveisCompativeis = imovel?.permutas_imoveis_compativeis || []
  const permutasAutomoveisCompativeis = imovel?.permutas_automoveis_compativeis || []

  const handleDelete = async () => {
    const result = await swal.fire({
      title: 'Tem certeza?',
      text: 'Esta ação não pode ser desfeita. O imóvel será excluído permanentemente.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#64748b',
      confirmButtonText: 'Sim, excluir!',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed) {
      try {
        await api.delete(`/imovel/${id}/`)
        swal.fire({
          title: 'Excluído!',
          text: 'O imóvel foi excluído com sucesso.',
          icon: 'success',
          timer: 2000,
          showConfirmButton: false
        })
        navigate('/imoveis')
      } catch (error) {
        swal.fire('Erro', 'Não foi possível excluir o imóvel.', 'error')
      }
    }
  }

  const handleEdit = () => {
    setIsModalOpen(true)
  }

  const handleDeleteInteresseImovel = async (interesseId: number) => {
    const result = await swal.fire({
      title: 'Excluir interesse?',
      text: 'Esta ação não pode ser desfeita.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#64748b',
      confirmButtonText: 'Sim, excluir!',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed) {
      try {
        await api.delete(`/imovel/interesse/imovel/${interesseId}/`)
        fetchData()
        swal.fire({
          title: 'Excluído!',
          text: 'Interesse removido com sucesso.',
          icon: 'success',
          timer: 1500,
          showConfirmButton: false
        })
      } catch (error) {
        swal.fire('Erro', 'Não foi possível excluir o interesse.', 'error')
      }
    }
  }

  const handleDeleteInteresseAutomovel = async (interesseId: number) => {
    const result = await swal.fire({
      title: 'Excluir interesse?',
      text: 'Esta ação não pode ser desfeita.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#64748b',
      confirmButtonText: 'Sim, excluir!',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed) {
      try {
        await api.delete(`/imovel/interesse/automovel/${interesseId}/`)
        fetchData()
        swal.fire({
          title: 'Excluído!',
          text: 'Interesse removido com sucesso.',
          icon: 'success',
          timer: 1500,
          showConfirmButton: false
        })
      } catch (error) {
        swal.fire('Erro', 'Não foi possível excluir o interesse.', 'error')
      }
    }
  }

  const handleEditInteresseImovel = (interesse: InteresseImovelType) => {
    setEditingInteresseImovel(interesse)
    setIsInteresseImovelModalOpen(true)
  }

  const handleEditInteresseAutomovel = (interesse: InteresseAutomovelType) => {
    setEditingInteresseAutomovel(interesse)
    setIsInteresseAutomovelModalOpen(true)
  }

  const handleSaveInteresseImovel = async (data: InteresseImovelData) => {
    if (!editingInteresseImovel) return
    try {
      await api.patch(`/imovel/interesse/imovel/${editingInteresseImovel.id}/`, {
        tipo_imovel: data.tipo_imovel ? parseInt(data.tipo_imovel) : null,
        zona: data.zona ? parseInt(data.zona) : null,
        estado: data.estado || null,
        valor_minimo: data.valor_minimo ? parseFloat(data.valor_minimo) : null,
        valor_maximo: data.valor_maximo ? parseFloat(data.valor_maximo) : null,
        observacoes: data.observacoes || ''
      })
      fetchData()
      setIsInteresseImovelModalOpen(false)
      setEditingInteresseImovel(null)
    } catch (error) {
      swal.fire('Erro', 'Não foi possível atualizar o interesse.', 'error')
    }
  }

  const handleSaveInteresseAutomovel = async (data: InteresseAutomovelData) => {
    if (!editingInteresseAutomovel) return
    try {
      await api.patch(`/imovel/interesse/automovel/${editingInteresseAutomovel.id}/`, {
        tipo_automovel: data.tipo_automovel ? parseInt(data.tipo_automovel) : null,
        valor_minimo: data.valor_minimo ? parseFloat(data.valor_minimo) : null,
        valor_maximo: data.valor_maximo ? parseFloat(data.valor_maximo) : null
      })
      fetchData()
      setIsInteresseAutomovelModalOpen(false)
      setEditingInteresseAutomovel(null)
    } catch (error) {
      swal.fire('Erro', 'Não foi possível atualizar o interesse.', 'error')
    }
  }

  if (loading || !imovel) {
    return (
      <Container>
        <LoadingScreen />
      </Container>
    )
  }

  return (
    <>
      <Container>
        <Banner>
          <Image />
          <Infos>
            <DescritivoContainer>
              <div>
                <Ref>{imovel.ref}</Ref>
                <Valor>{formatCurrency(imovel.valor_venda)}</Valor>
                <CorretorTipo>
                  <Corretor>{imovel.corretor}</Corretor>
                  <Tipo>{imovel.tipo_nome || '-'}{imovel.zona_nome ? ` - ${imovel.zona_nome}` : ''}</Tipo>
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
              <ActionButtons>
                <ActionButton onClick={handleEdit} title="Editar">
                  <EditIcon size={18} />
                </ActionButton>
                <ActionButton $variant="delete" onClick={handleDelete} title="Excluir">
                  <DeleteIcon size={18} />
                </ActionButton>
              </ActionButtons>
            </Proprietario>
          </Infos>
        </Banner>

        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title="Editar Imóvel"
        >
          <ImovelForm
            onSuccess={() => {
              fetchData()
              handleCloseModal()
            }}
            onClose={handleCloseModal}
            initialData={imovel}
          />
        </Modal>

        <Sections>
          <Interesses>
            <TituloSecao>Interesses Cadastrados</TituloSecao>
            <TableTitle>Imóveis</TableTitle>
            <Table>
              <thead>
                <TableRow>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Zona</TableHead>
                  <TableHead>Valor Máximo</TableHead>
                  <TableHead>Valor Mínimo</TableHead>
                  <TableHead style={{ width: '80px', textAlign: 'center' }}>Ações</TableHead>
                </TableRow>
              </thead>
              <tbody>
                {interessesImoveis.map((item: InteresseImovelType, index: number) => (
                  <TableRow key={index}>
                    <TableCell>{item.tipo_imovel_nome || 'Todos'}</TableCell>
                    <TableCell>{item.estado || '-'}</TableCell>
                    <TableCell>{item.zona_nome || 'Todas'}</TableCell>
                    <TableCell>{formatCurrency(item.valor_maximo)}</TableCell>
                    <TableCell>{formatCurrency(item.valor_minimo)}</TableCell>
                    <TableCell style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                      <ActionButton onClick={() => handleEditInteresseImovel(item)} title="Editar">
                        <EditIcon size={16} />
                      </ActionButton>
                      <ActionButton $variant="delete" onClick={() => handleDeleteInteresseImovel(item.id)} title="Excluir">
                        <DeleteIcon size={16} />
                      </ActionButton>
                    </TableCell>
                  </TableRow>
                ))}
              </tbody>
            </Table>
            <TableTitle>Automóveis</TableTitle>
            <Table>
              <thead>
                <TableRow>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Valor Máximo</TableHead>
                  <TableHead>Valor Mínimo</TableHead>
                  <TableHead style={{ width: '80px', textAlign: 'center' }}>Ações</TableHead>
                </TableRow>
              </thead>
              <tbody>
                {interessesAutomoveis.map((item: InteresseAutomovelType, index: number) => (
                  <TableRow key={index}>
                    <TableCell>{item.tipo_automovel_nome || 'Todos'}</TableCell>
                    <TableCell>{formatCurrency(item.valor_maximo)}</TableCell>
                    <TableCell>{formatCurrency(item.valor_minimo)}</TableCell>
                    <TableCell style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                      <ActionButton onClick={() => handleEditInteresseAutomovel(item)} title="Editar">
                        <EditIcon size={16} />
                      </ActionButton>
                      <ActionButton $variant="delete" onClick={() => handleDeleteInteresseAutomovel(item.id)} title="Excluir">
                        <DeleteIcon size={16} />
                      </ActionButton>
                    </TableCell>
                  </TableRow>
                ))}
              </tbody>
            </Table>
          </Interesses>

          {editingInteresseImovel && (
            <Modal
              isOpen={isInteresseImovelModalOpen}
              onClose={() => {
                setIsInteresseImovelModalOpen(false)
                setEditingInteresseImovel(null)
              }}
              title="Editar Interesse de Imóvel"
            >
              <InteresseImovelForm
                onAdd={handleSaveInteresseImovel}
                onClose={() => {
                  setIsInteresseImovelModalOpen(false)
                  setEditingInteresseImovel(null)
                }}
                initialData={{
                  tipo_imovel: editingInteresseImovel.tipo_imovel,
                  zona: editingInteresseImovel.zona,
                  estado: editingInteresseImovel.estado,
                  valor_minimo: editingInteresseImovel.valor_minimo,
                  valor_maximo: editingInteresseImovel.valor_maximo,
                  observacoes: editingInteresseImovel.observacoes
                }}
              />
            </Modal>
          )}

          {editingInteresseAutomovel && (
            <Modal
              isOpen={isInteresseAutomovelModalOpen}
              onClose={() => {
                setIsInteresseAutomovelModalOpen(false)
                setEditingInteresseAutomovel(null)
              }}
              title="Editar Interesse de Automóvel"
            >
              <InteresseAutomovelForm
                onAdd={handleSaveInteresseAutomovel}
                onClose={() => {
                  setIsInteresseAutomovelModalOpen(false)
                  setEditingInteresseAutomovel(null)
                }}
                initialData={{
                  tipo_automovel: editingInteresseAutomovel.tipo_automovel,
                  valor_minimo: editingInteresseAutomovel.valor_minimo,
                  valor_maximo: editingInteresseAutomovel.valor_maximo
                }}
              />
            </Modal>
          )}

          <TituloSecao>Imóveis Compatíveis</TituloSecao>
          <Permutas>
            <PermutaSection>
              <TableTitle>
                Este imóvel busca ({imovel.imoveis_compativeis?.length || 0})
              </TableTitle>
              {imovel.imoveis_compativeis?.length > 0 ? (
                imovel.imoveis_compativeis.map(
                  (imovelMatch: ImovelCompativelType, index: number) => (
                    <MatchCard 
                      key={index}
                      onClick={() => navigate(`/imovel/${imovelMatch.id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <MatchBadge>Match</MatchBadge>
                      <MatchCardTitle>{imovelMatch.ref}</MatchCardTitle>
                      <MatchCardDetail>{imovelMatch.tipo_nome || '-'}{imovelMatch.zona_nome ? ` - ${imovelMatch.zona_nome}` : ''}</MatchCardDetail>
                      <MatchCardDetail>{imovelMatch.condominio_nome || '-'}</MatchCardDetail>
                      <MatchCardDetail>{imovelMatch.condominio_bairro || '-'}</MatchCardDetail>
                      <MatchCardDetail>
                        Proprietário: {imovelMatch.proprietario_nome || '-'}
                      </MatchCardDetail>
                      <MatchCardValue>{formatCurrency(imovelMatch.valor_venda)}</MatchCardValue>
                    </MatchCard>
                  )
                )
              ) : (
                <p
                  style={{
                    color: '#64748b',
                    textAlign: 'center',
                    padding: '24px'
                  }}
                >
                  Nenhum imóvel compatível encontrado
                </p>
              )}
            </PermutaSection>
            <PermutaSection>
              <TableTitle>
                Buscam este imóvel ({imovel.imoveis_interessados?.length || 0})
              </TableTitle>
              {imovel.imoveis_interessados?.length > 0 ? (
                imovel.imoveis_interessados.map(
                  (imovelMatch: ImovelCompativelType, index: number) => (
                    <MatchCard 
                      key={index}
                      onClick={() => navigate(`/imovel/${imovelMatch.id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <MatchBadge>Interessado</MatchBadge>
                      <MatchCardTitle>{imovelMatch.ref}</MatchCardTitle>
                      <MatchCardDetail>{imovelMatch.tipo_nome || '-'}{imovelMatch.zona_nome ? ` - ${imovelMatch.zona_nome}` : ''}</MatchCardDetail>
                      <MatchCardDetail>{imovelMatch.condominio_nome || '-'}</MatchCardDetail>
                      <MatchCardDetail>{imovelMatch.condominio_bairro || '-'}</MatchCardDetail>
                      <MatchCardDetail>
                        Proprietário: {imovelMatch.proprietario_nome || '-'}
                      </MatchCardDetail>
                      <MatchCardValue>{formatCurrency(imovelMatch.valor_venda)}</MatchCardValue>
                    </MatchCard>
                  )
                )
              ) : (
                <p
                  style={{
                    color: '#64748b',
                    textAlign: 'center',
                    padding: '24px'
                  }}
                >
                  Nenhum imóvel interessado encontrado
                </p>
              )}
            </PermutaSection>
          </Permutas>

          <TituloSecao>Permutas Compatíveis</TituloSecao>
          <Permutas>
            <PermutaSection>
              <TableTitle>
                Imóveis ({permutasImoveisCompativeis.length})
              </TableTitle>
              {permutasImoveisCompativeis.length > 0 ? (
                permutasImoveisCompativeis.map(
                  (permutaImovel: PermutaImovelCompativelType, index: number) => (
                    <MatchCard 
                      key={index}
                      onClick={() => navigate(`/permuta/imovel/${permutaImovel.id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <MatchBadge>Match</MatchBadge>
                      <MatchCardTitle>{permutaImovel.tipo_nome || '-'}</MatchCardTitle>
                      <MatchCardDetail>
                        {permutaImovel.estado} - {permutaImovel.zona_nome || '-'}
                      </MatchCardDetail>
                      <MatchCardDetail>{permutaImovel.bairro}</MatchCardDetail>
                      <MatchCardDetail>
                        {permutaImovel.condominio}
                      </MatchCardDetail>
                      <MatchCardDetail>
                        Proprietário: {permutaImovel.proprietario_nome}
                      </MatchCardDetail>
                      <MatchCardValue>{formatCurrency(permutaImovel.valor)}</MatchCardValue>
                    </MatchCard>
                  )
                )
              ) : (
                <p
                  style={{
                    color: '#64748b',
                    textAlign: 'center',
                    padding: '24px'
                  }}
                >
                  Nenhum imóvel compatível encontrado
                </p>
              )}
            </PermutaSection>
            <PermutaSection>
              <TableTitle>
                Automóveis ({permutasAutomoveisCompativeis.length})
              </TableTitle>
              {permutasAutomoveisCompativeis.length > 0 ? (
                permutasAutomoveisCompativeis.map(
                  (permutaAutomovel: PermutaAutomovelCompativelType, index: number) => (
                    <MatchCard 
                      key={index}
                      onClick={() => navigate(`/permuta/automovel/${permutaAutomovel.id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <MatchBadge>Match</MatchBadge>
                      <MatchCardTitle>{permutaAutomovel.tipo_nome || '-'}</MatchCardTitle>
                      <MatchCardDetail>
                        {permutaAutomovel.marca} {permutaAutomovel.modelo}
                      </MatchCardDetail>
                      <MatchCardDetail>
                        Motor: {permutaAutomovel.motor || '-'}
                      </MatchCardDetail>
                      <MatchCardDetail>
                        Proprietário: {permutaAutomovel.proprietario_nome}
                      </MatchCardDetail>
                      <MatchCardValue>{formatCurrency(permutaAutomovel.valor)}</MatchCardValue>
                    </MatchCard>
                  )
                )
              ) : (
                <p
                  style={{
                    color: '#64748b',
                    textAlign: 'center',
                    padding: '24px'
                  }}
                >
                  Nenhum automóvel compatível encontrado
                </p>
              )}
            </PermutaSection>
          </Permutas>
        </Sections>
      </Container>
    </>
  )
}

export default Imovel
