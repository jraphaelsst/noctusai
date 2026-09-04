import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import styled from 'styled-components'
import { color, radius, spacing, breakpoints } from '../../styles'

const LandingContainer = styled.div`
  min-height: 100vh;
  background: linear-gradient(
    135deg,
    ${color.secondary} 0%,
    ${color.secondaryLight} 100%
  );
`

const Header = styled.header`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${spacing.lg} ${spacing.xxl};
  max-width: 1400px;
  margin: 0 auto;

  @media (max-width: ${breakpoints.tablet}) {
    padding: ${spacing.md};
  }
`

const Logo = styled.h1`
  font-size: 1.5rem;
  font-weight: 700;
  color: ${color.textInverse};
`

const NavLinks = styled.div`
  display: flex;
  gap: ${spacing.md};
`

const NavLink = styled(Link)`
  padding: ${spacing.sm} ${spacing.lg};
  border-radius: ${radius.md};
  font-weight: 500;

  text-decoration: none;
  transition: all 0.2s ease;
  color: ${color.textInverse};

  &:hover {
    background: rgba(255, 255, 255, 0.1);
  }
`

const LoginButton = styled(Link)`
  padding: ${spacing.sm} ${spacing.lg};
  border-radius: ${radius.md};
  background: ${color.primary};
  color: ${color.textInverse};
  font-weight: 600;
  transition: all 0.2s ease;

  &:hover {
    background: ${color.primaryLight};
    transform: translateY(-1px);
  }
`

const Hero = styled.section`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: ${spacing.xxl};
  min-height: 80vh;
  max-width: 900px;
  margin: 0 auto;

  @media (max-width: ${breakpoints.tablet}) {
    padding: ${spacing.lg};
    min-height: 60vh;
  }
`

const HeroTitle = styled.h1`
  font-size: 3.5rem;
  font-weight: 800;
  color: ${color.textInverse};
  margin-bottom: ${spacing.lg};
  line-height: 1.1;

  @media (max-width: ${breakpoints.tablet}) {
    font-size: 2rem;
  }
`

const HeroSubtitle = styled.p`
  font-size: 1.25rem;
  color: rgba(255, 255, 255, 0.8);
  margin-bottom: ${spacing.xl};
  max-width: 600px;

  @media (max-width: ${breakpoints.tablet}) {
    font-size: 1rem;
  }
`

const CTAButton = styled(Link)`
  display: inline-flex;
  align-items: center;
  gap: ${spacing.sm};
  padding: ${spacing.md} ${spacing.xl};
  background: linear-gradient(
    135deg,
    ${color.primary} 0%,
    ${color.primaryDark} 100%
  );
  color: ${color.textInverse};
  font-size: 1.1rem;
  font-weight: 600;
  text-decoration: none;
  border-radius: ${radius.lg};
  box-shadow: 0 4px 20px rgba(235, 235, 235, 0.2);
  transition: all 0.3s ease;

  &:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 30px rgba(235, 235, 235, 0.3);
  }
`

const Features = styled.section`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: ${spacing.xl};
  padding: ${spacing.xxl};
  max-width: 1200px;
  margin: 0 auto;

  @media (max-width: ${breakpoints.desktop}) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
  }
`

const FeatureCard = styled.div`
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: ${radius.xl};
  padding: ${spacing.xl};
  text-align: center;
  transition: all 0.3s ease;

  &:hover {
    transform: translateY(-5px);
    background: rgba(255, 255, 255, 0.1);
  }
`

const FeatureIcon = styled.div`
  width: 60px;
  height: 60px;
  background: linear-gradient(
    135deg,
    ${color.primary} 0%,
    ${color.primaryDark} 100%
  );
  border-radius: ${radius.lg};
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto ${spacing.lg};
  font-size: 1.5rem;
`

const FeatureTitle = styled.h3`
  font-size: 1.25rem;
  font-weight: 600;
  color: ${color.textInverse};
  margin-bottom: ${spacing.sm};
`

const FeatureDescription = styled.p`
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
  line-height: 1.6;
`

const Landing = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  useEffect(() => {
    localStorage.getItem('authTokens')
      ? setIsAuthenticated(true)
      : setIsAuthenticated(false)
  }, [])

  return (
    <LandingContainer>
      <Header>
        <Logo></Logo>
        <NavLinks>
          {isAuthenticated ? (
            <LoginButton to="/home">Acessar Sistema</LoginButton>
          ) : (
            <NavLink to="/login">Entrar</NavLink>
          )}
        </NavLinks>
      </Header>

      <Hero>
        <HeroTitle>Sistema de Permutas Imobiliárias</HeroTitle>
        <HeroSubtitle>
          Encontre as melhores oportunidades de negócio através do cruzamento
          inteligente de critérios entre imóveis e interesses.
        </HeroSubtitle>
        <CTAButton to={isAuthenticated ? '/home' : '/login'}>
          {isAuthenticated ? 'Acessar Dashboard' : 'Começar Agora'}
        </CTAButton>
      </Hero>

      <Features>
        <FeatureCard>
          <FeatureIcon>🏠</FeatureIcon>
          <FeatureTitle>Gestão de Imóveis</FeatureTitle>
          <FeatureDescription>
            Cadastre e gerencie seus imóveis de forma simples e organizada.
          </FeatureDescription>
        </FeatureCard>
        <FeatureCard>
          <FeatureIcon>🔄</FeatureIcon>
          <FeatureTitle>Matching Inteligente</FeatureTitle>
          <FeatureDescription>
            Encontre permutas compatíveis automaticamente baseado em seus
            critérios.
          </FeatureDescription>
        </FeatureCard>
        <FeatureCard>
          <FeatureIcon>👥</FeatureIcon>
          <FeatureTitle>Gestão de Clientes</FeatureTitle>
          <FeatureDescription>
            Mantenha seus clientes e proprietários sempre organizados.
          </FeatureDescription>
        </FeatureCard>
      </Features>
    </LandingContainer>
  )
}

export default Landing
