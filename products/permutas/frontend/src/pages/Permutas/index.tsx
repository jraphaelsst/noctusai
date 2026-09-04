import { useState, useEffect, useCallback, useRef } from 'react'
import { formatCurrency } from '../../utils/formatCurrency'
import { useNavigate } from 'react-router-dom'
import swal from 'sweetalert2'
import styled from 'styled-components'
import Container from '../../containers/Container'
import Modal from '../../components/Modal'
import PermutaForm from '../../components/ModalForms/PermutaForm'
import PermutaImovelEditForm from '../../components/ModalForms/PermutaImovelEditForm'
import PermutaAutomovelEditForm from '../../components/ModalForms/PermutaAutomovelEditForm'
import DataTable, { Column } from '../../components/DataTable'
import Button from '../../components/Button'
import Pagination from '../../components/Pagination'
import { color, spacing, radius } from '../../styles'
import useAxios from '../../utils/useAxios'
const SectionTitle = styled.h3`
  margin-top: ${spacing.xl};
  margin-bottom: ${spacing.md};
  color: ${color.secondary};
  font-size: 18px;
  font-weight: 600;
  padding-bottom: ${spacing.sm};
  border-bottom: 2px solid ${color.primary};
`

const TabContainer = styled.div`
  display: flex;
  gap: ${spacing.sm};
  margin-bottom: ${spacing.lg};
`

const Tab = styled.button<{ $active: boolean }>`
  padding: ${spacing.sm} ${spacing.lg};
  border: none;
  border-radius: ${radius.md};
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  background: ${({ $active }) => $active ? color.primary : color.backgroundDark};
  color: ${({ $active }) => $active ? 'white' : color.text};

  &:hover {
    background: ${({ $active }) => $active ? color.primaryDark : color.border};
  }
`

export type PermutaImovelType = {
  id: number
  codigo: string
  ref: string | null
  criado_por: number
  criado_por_nome: string
  corretor: number | null
  corretor_nome: string | null
  proprietario: number
  proprietario_nome: string
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
}

export type PermutaAutomovelType = {
  id: number
  codigo: string
  criado_por: number
  criado_por_nome: string
  corretor: number | null
  corretor_nome: string | null
  proprietario: number
  proprietario_nome: string
  tipo: number | null
  tipo_nome: string | null
  marca: string
  modelo: string
  motor: string
  valor: number
}

type PaginatedResponse<T> = {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const Permutas = () => {
  const [permutasImovel, setPermutasImovel] = useState<PermutaImovelType[]>([])
  const [permutasAutomovel, setPermutasAutomovel] = useState<PermutaAutomovelType[]>([])
  const [loadingImovel, setLoadingImovel] = useState(true)
  const [loadingAutomovel, setLoadingAutomovel] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<'imovel' | 'automovel'>('imovel')
  const [editingPermutaImovel, setEditingPermutaImovel] = useState<PermutaImovelType | null>(null)
  const [editingPermutaAutomovel, setEditingPermutaAutomovel] = useState<PermutaAutomovelType | null>(null)
  const [pageImovel, setPageImovel] = useState(1)
  const [pageAutomovel, setPageAutomovel] = useState(1)
  const [totalImovel, setTotalImovel] = useState(0)
  const [totalAutomovel, setTotalAutomovel] = useState(0)
  const [totalPagesImovel, setTotalPagesImovel] = useState(1)
  const [totalPagesAutomovel, setTotalPagesAutomovel] = useState(1)
  const [filtersImovel, setFiltersImovel] = useState<Record<string, string>>({})
  const [filtersAutomovel, setFiltersAutomovel] = useState<Record<string, string>>({})
  const navigate = useNavigate()
  const api = useAxios()
  const filtersImovelRef = useRef(filtersImovel)
  const filtersAutomovelRef = useRef(filtersAutomovel)
  filtersImovelRef.current = filtersImovel
  filtersAutomovelRef.current = filtersAutomovel

  const fetchPermutasImovel = useCallback(async (page: number = 1, filters: Record<string, string> = {}) => {
    setLoadingImovel(true)
    try {
      const params = new URLSearchParams()
      params.append('page', String(page))
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value)
      })
      const response = await api.get(`/permuta/imovel/?${params.toString()}`)
      const data = response.data as PaginatedResponse<PermutaImovelType>
      if (data.results) {
        if (data.results.length === 0 && page > 1) {
          setPageImovel(page - 1)
          return
        }
        setPermutasImovel(data.results)
        setTotalImovel(data.count)
        setTotalPagesImovel(Math.ceil(data.count / 10) || 1)
      } else {
        setPermutasImovel(Array.isArray(response.data) ? response.data : [])
      }
    } catch (error: any) {
      if (error?.response?.status === 404 && page > 1) {
        setPageImovel(page - 1)
        return
      }
      console.error('Error fetching permutas imovel:', error)
      setPermutasImovel([])
    } finally {
      setLoadingImovel(false)
    }
  }, [api])

  const fetchPermutasAutomovel = useCallback(async (page: number = 1, filters: Record<string, string> = {}) => {
    setLoadingAutomovel(true)
    try {
      const params = new URLSearchParams()
      params.append('page', String(page))
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value)
      })
      const response = await api.get(`/permuta/automovel/?${params.toString()}`)
      const data = response.data as PaginatedResponse<PermutaAutomovelType>
      if (data.results) {
        if (data.results.length === 0 && page > 1) {
          setPageAutomovel(page - 1)
          return
        }
        setPermutasAutomovel(data.results)
        setTotalAutomovel(data.count)
        setTotalPagesAutomovel(Math.ceil(data.count / 10) || 1)
      } else {
        setPermutasAutomovel(Array.isArray(response.data) ? response.data : [])
      }
    } catch (error: any) {
      if (error?.response?.status === 404 && page > 1) {
        setPageAutomovel(page - 1)
        return
      }
      console.error('Error fetching permutas automovel:', error)
      setPermutasAutomovel([])
    } finally {
      setLoadingAutomovel(false)
    }
  }, [api])

  useEffect(() => {
    fetchPermutasImovel(pageImovel, filtersImovelRef.current)
  }, [pageImovel])

  useEffect(() => {
    fetchPermutasAutomovel(pageAutomovel, filtersAutomovelRef.current)
  }, [pageAutomovel])

  const handleRefetch = () => {
    fetchPermutasImovel(pageImovel, filtersImovel)
    fetchPermutasAutomovel(pageAutomovel, filtersAutomovel)
  }

  const handleServerFilterImovel = useCallback((filters: Record<string, string>) => {
    setFiltersImovel(filters)
    setPageImovel(1)
    fetchPermutasImovel(1, filters)
  }, [fetchPermutasImovel])

  const handleServerFilterAutomovel = useCallback((filters: Record<string, string>) => {
    setFiltersAutomovel(filters)
    setPageAutomovel(1)
    fetchPermutasAutomovel(1, filters)
  }, [fetchPermutasAutomovel])

  const columnsImovel: Column<PermutaImovelType>[] = [
    { key: 'codigo', label: 'Código', filterable: true, filterKey: 'codigo' },
    { key: 'ref', label: 'Ref', filterable: true, filterKey: 'ref', render: (item) => item.ref || '-' },
    { key: 'proprietario_nome', label: 'Proprietário', filterable: true, filterKey: 'proprietario' },
    { 
      key: 'tipo', 
      label: 'Tipo',
      filterable: true,
      filterKey: 'tipo_nome',
      render: (item) => item.tipo_nome || '-'
    },
    { key: 'cidade', label: 'Cidade', filterable: true, filterKey: 'cidade' },
    { key: 'bairro', label: 'Bairro', filterable: true, filterKey: 'bairro' },
    { 
      key: 'zona', 
      label: 'Zona',
      render: (item) => item.zona_nome || '-'
    },
    { 
      key: 'valor', 
      label: 'Valor',
      render: (item) => formatCurrency(item.valor)
    },
  ]

  const columnsAutomovel: Column<PermutaAutomovelType>[] = [
    { key: 'codigo', label: 'Código', filterable: true, filterKey: 'codigo' },
    { key: 'proprietario_nome', label: 'Proprietário', filterable: true, filterKey: 'proprietario' },
    { 
      key: 'tipo', 
      label: 'Tipo',
      filterable: true,
      filterKey: 'tipo_nome',
      render: (item) => item.tipo_nome || '-'
    },
    { key: 'marca', label: 'Marca', filterable: true, filterKey: 'marca' },
    { key: 'modelo', label: 'Modelo', filterable: true, filterKey: 'modelo' },
    { 
      key: 'motor', 
      label: 'Motor',
      render: (item) => item.motor || '-'
    },
    { 
      key: 'valor', 
      label: 'Valor',
      render: (item) => formatCurrency(item.valor)
    },
  ]

  const handleViewImovel = (permuta: PermutaImovelType) => {
    navigate(`/permuta/imovel/${permuta.id}`)
  }

  const handleViewAutomovel = (permuta: PermutaAutomovelType) => {
    navigate(`/permuta/automovel/${permuta.id}`)
  }

  const handleDeleteImovel = async (permuta: PermutaImovelType) => {
    try {
      await api.delete(`/permuta/imovel/${permuta.id}/`)
      swal.fire('Sucesso', 'Permuta excluída com sucesso!', 'success')
      fetchPermutasImovel(pageImovel, filtersImovel)
    } catch (error) {
      swal.fire('Erro', 'Não foi possível excluir a permuta.', 'error')
    }
  }

  const handleDeleteAutomovel = async (permuta: PermutaAutomovelType) => {
    try {
      await api.delete(`/permuta/automovel/${permuta.id}/`)
      swal.fire('Sucesso', 'Permuta excluída com sucesso!', 'success')
      fetchPermutasAutomovel(pageAutomovel, filtersAutomovel)
    } catch (error) {
      swal.fire('Erro', 'Não foi possível excluir a permuta.', 'error')
    }
  }

  const handleEditImovel = (permuta: PermutaImovelType) => {
    setEditingPermutaImovel(permuta)
    setEditingPermutaAutomovel(null)
    setIsEditModalOpen(true)
  }

  const handleEditAutomovel = (permuta: PermutaAutomovelType) => {
    setEditingPermutaAutomovel(permuta)
    setEditingPermutaImovel(null)
    setIsEditModalOpen(true)
  }

  const handleCloseEditModal = () => {
    setIsEditModalOpen(false)
    setEditingPermutaImovel(null)
    setEditingPermutaAutomovel(null)
  }

  return (
    <Container title="Permutas">
      <Button type="button" onClick={() => setIsModalOpen(true)}>
        Cadastrar Nova
      </Button>

      <TabContainer>
        <Tab $active={activeTab === 'imovel'} onClick={() => setActiveTab('imovel')}>
          Imóveis
        </Tab>
        <Tab $active={activeTab === 'automovel'} onClick={() => setActiveTab('automovel')}>
          Automóveis
        </Tab>
      </TabContainer>

      {activeTab === 'imovel' ? (
        <>
          <SectionTitle>Permutas de Imóveis</SectionTitle>
          <DataTable
            data={permutasImovel || []}
            columns={columnsImovel}
            onView={handleViewImovel}
            onEdit={handleEditImovel}
            onDelete={handleDeleteImovel}
            deleteConfirmMessage="Tem certeza que deseja excluir esta permuta?"
            loading={loadingImovel}
            serverFiltering={true}
            onServerFilter={handleServerFilterImovel}
            totalCount={totalImovel}
          />
          <Pagination
            currentPage={pageImovel}
            totalPages={totalPagesImovel}
            totalCount={totalImovel}
            onPageChange={setPageImovel}
          />
        </>
      ) : (
        <>
          <SectionTitle>Permutas de Automóveis</SectionTitle>
          <DataTable
            data={permutasAutomovel || []}
            columns={columnsAutomovel}
            onView={handleViewAutomovel}
            onEdit={handleEditAutomovel}
            onDelete={handleDeleteAutomovel}
            deleteConfirmMessage="Tem certeza que deseja excluir esta permuta?"
            loading={loadingAutomovel}
            serverFiltering={true}
            onServerFilter={handleServerFilterAutomovel}
            totalCount={totalAutomovel}
          />
          <Pagination
            currentPage={pageAutomovel}
            totalPages={totalPagesAutomovel}
            totalCount={totalAutomovel}
            onPageChange={setPageAutomovel}
          />
        </>
      )}

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Nova Permuta"
      >
        <PermutaForm
          onSuccess={() => {
            handleRefetch()
            setIsModalOpen(false)
          }}
          onClose={() => setIsModalOpen(false)}
        />
      </Modal>

      <Modal
        isOpen={isEditModalOpen && editingPermutaImovel !== null}
        onClose={handleCloseEditModal}
        title="Editar Permuta de Imóvel"
      >
        {editingPermutaImovel && (
          <PermutaImovelEditForm
            onSuccess={() => {
              fetchPermutasImovel(pageImovel, filtersImovel)
              handleCloseEditModal()
            }}
            onClose={handleCloseEditModal}
            initialData={editingPermutaImovel}
          />
        )}
      </Modal>

      <Modal
        isOpen={isEditModalOpen && editingPermutaAutomovel !== null}
        onClose={handleCloseEditModal}
        title="Editar Permuta de Automóvel"
      >
        {editingPermutaAutomovel && (
          <PermutaAutomovelEditForm
            onSuccess={() => {
              fetchPermutasAutomovel(pageAutomovel, filtersAutomovel)
              handleCloseEditModal()
            }}
            onClose={handleCloseEditModal}
            initialData={editingPermutaAutomovel}
          />
        )}
      </Modal>
    </Container>
  )
}

export default Permutas
