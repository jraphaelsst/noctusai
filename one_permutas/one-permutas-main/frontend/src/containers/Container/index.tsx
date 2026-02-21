import { GlobalContainer, Title } from './styles'

type Props = {
  title: string
  children: JSX.Element | JSX.Element[]
}

const Container = ({ title, children }: Props) => {
  return (
    <GlobalContainer>
      <Title>{title}</Title>
      {children}
    </GlobalContainer>
  )
}

export default Container
