import { GlobalContainer, Title } from './styles'

type Props = {
  title?: string
  children: React.ReactNode
}

const Container = ({ title, children }: Props) => {
  return (
    <GlobalContainer>
      {title && <Title>{title}</Title>}
      {children}
    </GlobalContainer>
  )
}

export default Container
