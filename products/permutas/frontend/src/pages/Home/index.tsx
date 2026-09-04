import { useState } from 'react'
import { Link } from 'react-router-dom'
import styled from 'styled-components'
import { color, spacing, breakpoints } from '../../styles'
import Modal from '../../components/Modal'
import ImovelForm from '../../components/ModalForms/ImovelForm'
import ClienteForm from '../../components/ModalForms/ClienteForm'
import CondominioForm from '../../components/ModalForms/CondominioForm'
import PermutaForm from '../../components/ModalForms/PermutaForm'

const DashboardContainer = styled.div`
  width: 100%;
  min-height: 100vh;
  
  background: ${color.background};
`

const DashboardContent = styled.div`
  width: 80%;
  margin: 0 auto;
  padding: ${spacing.xxl} ${spacing.lg};

  @media (max-width: ${breakpoints.tablet}) {
    padding: ${spacing.lg};
  }
`

const WelcomeSection = styled.div`
  background: ${color.primary};
  padding: ${spacing.xxl};
  margin-bottom: ${spacing.xl};
  color: ${color.textInverse};
`

const WelcomeTitle = styled.h1`
  font-size: 1.75rem;
  font-weight: 600;
  margin-bottom: ${spacing.sm};
  color: ${color.textInverse};
`

const WelcomeSubtitle = styled.p`
  font-size: 1rem;
  opacity: 0.9;
`

const QuickActionsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: ${spacing.lg};
  margin-bottom: ${spacing.xl};

  @media (max-width: ${breakpoints.desktop}) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: ${breakpoints.smartphone}) {
    grid-template-columns: 1fr;
  }
`

const QuickActionCard = styled.button`
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: ${spacing.xl};
  background: ${color.cardBg};
  border: 1px solid ${color.border};
  text-decoration: none;
  transition: all 0.2s ease;
  cursor: pointer;

  &:hover {
    border-color: ${color.primary};
    background: ${color.backgroundDark};
  }
`

const ActionIcon = styled.div`
  width: 56px;
  height: 56px;
  background: ${color.backgroundDark};
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: ${spacing.md};
  font-size: 1.5rem;
`

const ActionTitle = styled.h3`
  font-size: 1rem;
  font-weight: 600;
  color: ${color.text};
  margin-bottom: ${spacing.xs};
`

const ActionDescription = styled.p`
  font-size: 13px;
  color: ${color.textLight};
  text-align: center;
`

const StatsSection = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: ${spacing.lg};

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
  }
`

const StatCard = styled(Link)`
  display: block;
  background: ${color.cardBg};
  padding: ${spacing.xl};
  border: 1px solid ${color.border};
  text-decoration: none;
  transition: all 0.2s ease;

  &:hover {
    border-color: ${color.primary};
  }
`

const StatValue = styled.div`
  font-size: 2.5rem;
  font-weight: 700;
  color: ${color.primary};
  margin-bottom: ${spacing.xs};
`

const StatLabel = styled.div`
  font-size: 14px;
  color: ${color.textLight};
`

const Home = () => {
  const [isImovelModalOpen, setIsImovelModalOpen] = useState(false)
  const [isClienteModalOpen, setIsClienteModalOpen] = useState(false)
  const [isCondominioModalOpen, setIsCondominioModalOpen] = useState(false)
  const [isPermutaModalOpen, setIsPermutaModalOpen] = useState(false)

  return (
    <DashboardContainer>
      <DashboardContent>
        <WelcomeSection>
          <WelcomeTitle>Bem-vindo ao Sistema de Permutas</WelcomeTitle>
          <WelcomeSubtitle>
            Gerencie seus imóveis e encontre as melhores oportunidades de
            negócio
          </WelcomeSubtitle>
        </WelcomeSection>

        <QuickActionsGrid>
          <QuickActionCard onClick={() => setIsImovelModalOpen(true)}>
            <ActionIcon>🏠</ActionIcon>
            <ActionTitle>Novo Imóvel</ActionTitle>
            <ActionDescription>Cadastrar um novo imóvel</ActionDescription>
          </QuickActionCard>
          <QuickActionCard onClick={() => setIsPermutaModalOpen(true)}>
            <ActionIcon>🔄</ActionIcon>
            <ActionTitle>Nova Permuta</ActionTitle>
            <ActionDescription>Cadastrar nova permuta</ActionDescription>
          </QuickActionCard>
          <QuickActionCard onClick={() => setIsClienteModalOpen(true)}>
            <ActionIcon>👤</ActionIcon>
            <ActionTitle>Novo Cliente</ActionTitle>
            <ActionDescription>Cadastrar novo cliente</ActionDescription>
          </QuickActionCard>
          <QuickActionCard onClick={() => setIsCondominioModalOpen(true)}>
            <ActionIcon>🏢</ActionIcon>
            <ActionTitle>Novo Condomínio</ActionTitle>
            <ActionDescription>Cadastrar novo condomínio</ActionDescription>
          </QuickActionCard>
        </QuickActionsGrid>

        <StatsSection>
          <StatCard to="/imoveis">
            <StatValue>--</StatValue>
            <StatLabel>Imóveis Cadastrados</StatLabel>
          </StatCard>
          <StatCard to="/permutas">
            <StatValue>--</StatValue>
            <StatLabel>Permutas Disponíveis</StatLabel>
          </StatCard>
          <StatCard to="/matches">
            <StatValue>--</StatValue>
            <StatLabel>Matches Encontrados</StatLabel>
          </StatCard>
        </StatsSection>
      </DashboardContent>

      <Modal
        isOpen={isImovelModalOpen}
        onClose={() => setIsImovelModalOpen(false)}
        title="Novo Imóvel"
      >
        <ImovelForm
          onSuccess={() => setIsImovelModalOpen(false)}
          onClose={() => setIsImovelModalOpen(false)}
        />
      </Modal>

      <Modal
        isOpen={isClienteModalOpen}
        onClose={() => setIsClienteModalOpen(false)}
        title="Novo Cliente"
      >
        <ClienteForm
          onSuccess={() => setIsClienteModalOpen(false)}
          onClose={() => setIsClienteModalOpen(false)}
        />
      </Modal>

      <Modal
        isOpen={isCondominioModalOpen}
        onClose={() => setIsCondominioModalOpen(false)}
        title="Novo Condomínio"
      >
        <CondominioForm
          onSuccess={() => setIsCondominioModalOpen(false)}
          onClose={() => setIsCondominioModalOpen(false)}
        />
      </Modal>

      <Modal
        isOpen={isPermutaModalOpen}
        onClose={() => setIsPermutaModalOpen(false)}
        title="Nova Permuta"
      >
        <PermutaForm
          onSuccess={() => setIsPermutaModalOpen(false)}
          onClose={() => setIsPermutaModalOpen(false)}
        />
      </Modal>
    </DashboardContainer>
  )
}

export default Home
